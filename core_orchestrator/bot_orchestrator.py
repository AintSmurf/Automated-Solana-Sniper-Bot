import threading
import time
from services.open_positions import OpenPositionTracker
from connectors.helius_connector import HeliusConnector
from helpers.logging_manager import LoggingHandler
from notification.notification_manager import NotificationManager
from services.bot_context import BotContext
from core.solana_manager import SolanaManager
from services.volume_tracker import VolumeTracker
from helpers.rate_limiter import RateLimiter
from helpers.rug_check_utility import RugCheckUtility
from services.trade_counter import TradeCounter
from helpers.requests_utility import RequestsUtility
from config.third_parties import JUPITER_STATION,BIRDEYE
from config.network import HELIUS_URL,HELIUS_ENHANCED
from clients.wallet_client import WalletClient
from clients.birdeye_client import BirdeyeClient
from clients.jupiter_client import JupiterClient
from clients.helius_client import HeliusClient
from services.liquidity_analyzer import LiquidityAnalyzer
from services.scam_checker import ScamChecker
from core.transaction_manager import TransactionManager
import queue
from core.trade_manager import TraderManager
from threading import Lock
from services.sql_db_utility import SqlDBUtility
from dao.token_dao import TokenDAO
from dao.liquidity_dao import LiquidityDAO
from dao.volume_dao import VolumeDAO
from dao.scam_checker_dao import ScamCheckerDao
from dao.trade_dao import TradeDAO
from dao.signature_dao import SignatureDAO
from config.network import HELIUS_SENDER, DEFAULT_SENDER_REGION





logger = LoggingHandler.get_logger()


class BotOrchestrator:
    def __init__(self, ctx: BotContext):
        self.ctx = ctx 
        self.settings = self.ctx.settings

        # shared pipelines / caches
        ctx.register("prefetch_queue", queue.Queue(maxsize=1000))
        ctx.register("signature_queue", queue.Queue(maxsize=1000))

        # dedupe structures
        ctx.register("signature_seen", set())
        ctx.register("signature_seen_lock", Lock())
        

        ctx.register("sig_to_mint", {})
        ctx.register("pending_data", {})


        ctx.register("known_tokens", set())
        ctx.register("known_tokens_lock", Lock())
       
        # 1. Infrastructure
        rl_cfg = self.settings["RATE_LIMITS"]
        ctx.register("helius_rl", RateLimiter(**rl_cfg["helius"]))
        ctx.register("jupiter_rl", RateLimiter(**rl_cfg["jupiter"]))
        ctx.register("logger", LoggingHandler.get_logger())
        ctx.register("special_logger", LoggingHandler.get_special_debug_logger())
        ctx.register("tracker_logger", LoggingHandler.get_named_logger("tracker"))
        ctx.register("notification_manager", NotificationManager(ctx))


        #1.1 register db and dao
        ctx.register("sql_db", SqlDBUtility(ctx))
        ctx.register("token_dao",TokenDAO(ctx))
        ctx.register("liquidity_dao", LiquidityDAO(ctx))
        ctx.register("volume_dao", VolumeDAO(ctx))
        ctx.register("scam_checker_dao", ScamCheckerDao(ctx))
        ctx.register("trade_dao", TradeDAO(ctx))
        ctx.register("signatures_dao", SignatureDAO(ctx))


        # 2. Utilities  
        ctx.register("rug_check", RugCheckUtility())
        ctx.register("trade_counter", TradeCounter(self.settings["MAXIMUM_TRADES"]))
        ctx.register("liquidity_analyzer", LiquidityAnalyzer(ctx))
        ctx.register("scam_checker", ScamChecker(ctx))

        # 3. Transport / HTTP Clients
        ctx.register("helius_requests", RequestsUtility(HELIUS_URL[self.settings["NETWORK"]]))
        ctx.register("helius_enhanced", RequestsUtility(HELIUS_ENHANCED[self.settings["NETWORK"]]))
        ctx.register("jupiter_requests", RequestsUtility(JUPITER_STATION["BASE_URL"]))
        ctx.register("birdye_requests", RequestsUtility(BIRDEYE["BASE_URL"]))
        ctx.register("helius_sender_requests",RequestsUtility(HELIUS_SENDER[self.settings["USE_SENDER"]["REGION"]]))


        # 4. Domain clients
        ctx.register("helius_client", HeliusClient(ctx))
        ctx.register("jupiter_client", JupiterClient(ctx))
        ctx.register("birdeye_client", BirdeyeClient(ctx))
        ctx.register("wallet_client", WalletClient(ctx))

        # 5. Core logic
        ctx.register("trader", TraderManager(ctx))
        ctx.register("solana_manager", SolanaManager(ctx))
        ctx.register("transaction_manager", TransactionManager(ctx))

        # 6. Supporting services
        ctx.register("volume_tracker", VolumeTracker(ctx))
        ctx.register("open_position_tracker", OpenPositionTracker(ctx))


        self.logger = ctx.get("logger")
        self.tracker = ctx.get("open_position_tracker")
        self.transaction_handler = ctx.get("transaction_manager")
        self.notification_manager = ctx.get("notification_manager")
        self.trade_counter = ctx.get("trade_counter")
        self.trade_counter.reset()


        self.logger.info("✅ BotOrchestrator wiring complete")

        # Stop flags
        self.stops = {
            "ws": threading.Event(),
            "fetcher": threading.Event(),
            "tracker": threading.Event(),
        }

        
        # Core components
        self.helius_connector = HeliusConnector(
            ctx=ctx,
            stop_ws=self.stops["ws"],
        )

        self.threads: list[threading.Thread] = []
        
    def _safe_run(self, target, name, stop_event=None, *args):
        def wrapper():
            while not (stop_event and stop_event.is_set()):
                try:
                    if stop_event:
                        target(stop_event,*args)
                    else:
                        target(*args)
                except Exception as e:
                    logger.error(f"❌ Thread {name} crashed: {e}", exc_info=True)
                    time.sleep(2)
                else:
                    break 
        t = threading.Thread(target=wrapper, daemon=True, name=name)
        t.start()
        self.threads.append(t)

    def start(self):
        self._safe_run(self.helius_connector.start_ws, "WebSocket")
        self._safe_run(self.transaction_handler.run, "TxHandler", self.stops["fetcher"])
        self._safe_run(self.tracker.track_positions, "Tracker", self.stops["tracker"])
        self.notification_manager.start()

        logger.info("🚀 Bot started with all components")

    def run_cli_loop(self):
        """Blocking CLI watcher until trades complete."""
        while True:
            time.sleep(5)

            if self.trade_counter.reached_limit():
                logger.warning("🚫 MAX TRADES hit — stopping trade threads.")
                self.stops["ws"].set()
                self.stops["fetcher"].set()
                if not self.tracker.has_open_positions():
                    logger.info("✅ Trades done — shutting everything down.")
                    self.shutdown()
                    break

    def shutdown(self):
        """Graceful shutdown of trading threads and notifiers."""
        # 1. Stop all loops
        for stop in self.stops.values():
            stop.set()

        # 2. Close WS
        try:
            if hasattr(self, "helius_connector"):
                self.helius_connector.close()
        except Exception as e:
            logger.warning(f"⚠️ Failed to close WebSocket: {e}")

        # 3. Stop notifier
        try:
            self.notification_manager.shutdown()
        except Exception as e:
            logger.warning(f"⚠️ Notifier shutdown failed: {e}")

        # 4. Join worker threads
        for t in self.threads:
            if t.is_alive():
                t.join(timeout=2)

        logger.info("🛑 Bot fully shutdown.")
    
