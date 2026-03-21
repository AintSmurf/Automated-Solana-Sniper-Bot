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
from config.network import HELIUS_SENDER,HELIUS_WS
from dao.config_version_dao import ConfigVersionDAO
from dao.price_sample_dao import PriceSampleDAO
from services.trade_lifecycle_service import TradeLifecycleService
from services.trade_enrichment_service import TradeEnrichmentService
from services.token_discovery_persistence_service import TokenDiscoveryPersistenceService
from services.price_sample_recorder import PriceSampleRecorder
from services.wallet_reconciliation_service import WalletReconciliationService
from dao.run_session_dao import RunSessionDAO
from services.run_session_manager import RunSessionManager





class BotOrchestrator:
    def __init__(self, ctx: BotContext):
        self.ctx = ctx 
        self.settings = self.ctx.settings
        self.shutdown_started = False

        #register plain rpcs
        api_key = ctx.api_keys["helius"]
        ctx.register("rpc_url", HELIUS_URL[self.settings["NETWORK"]] + api_key)
        ctx.register("ws_url",  HELIUS_WS[self.settings["NETWORK"]] + api_key)


        # shared pipelines / caches
        ctx.register("prefetch_queue", queue.Queue(maxsize=1000))
        ctx.register("signature_queue", queue.Queue(maxsize=1000))

        # dedupe structures
        ctx.register("signature_seen", set())
        ctx.register("signature_seen_lock", Lock())     
        ctx.register("active_trades", {})
        ctx.register("active_trades_lock", Lock()) 
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


        #2. register db and dao
        ctx.register("sql_db", SqlDBUtility(ctx))
        ctx.register("token_dao",TokenDAO(ctx))
        ctx.register("liquidity_dao", LiquidityDAO(ctx))
        ctx.register("volume_dao", VolumeDAO(ctx))
        ctx.register("scam_checker_dao", ScamCheckerDao(ctx))
        ctx.register("trade_dao", TradeDAO(ctx))
        ctx.register("signatures_dao", SignatureDAO(ctx))
        ctx.register("price_sample_dao", PriceSampleDAO(ctx))
        ctx.register("config_version_dao", ConfigVersionDAO(ctx))
        ctx.register("run_session_dao", RunSessionDAO(ctx))


        # 3. Transport / HTTP Clients
        ctx.register("helius_requests", RequestsUtility(HELIUS_URL[self.settings["NETWORK"]]))
        ctx.register("helius_enhanced", RequestsUtility(HELIUS_ENHANCED[self.settings["NETWORK"]]))
        ctx.register("jupiter_requests", RequestsUtility(JUPITER_STATION["BASE_URL"]))
        ctx.register("birdeye_requests", RequestsUtility(BIRDEYE["BASE_URL"]))
        ctx.register("helius_sender_requests",RequestsUtility(HELIUS_SENDER[self.settings["USE_SENDER"]["REGION"]]))

        # 4. Domain clients
        ctx.register("helius_client", HeliusClient(ctx))
        ctx.register("jupiter_client", JupiterClient(ctx))
        ctx.register("birdeye_client", BirdeyeClient(ctx))
        ctx.register("wallet_client", WalletClient(ctx))

        # 5. Utilities  
        ctx.register("rug_check", RugCheckUtility())
        ctx.register("trade_counter", TradeCounter(self.settings["MAXIMUM_TRADES"]))
        ctx.register("liquidity_analyzer", LiquidityAnalyzer(ctx))
        ctx.register("scam_checker", ScamChecker(ctx))
        ctx.register("volume_tracker", VolumeTracker(ctx))
        ctx.register("price_sample_recorder", PriceSampleRecorder(ctx))
        ctx.register("wallet_reconciliation_service",WalletReconciliationService(ctx))
        ctx.register("run_session_manager", RunSessionManager(ctx))


        self.logger = ctx.get("logger")

        # id the run and the config      
        cfg_dao = ctx.get("config_version_dao")
        try:
            label = self.settings.get("RUN_LABEL") or "Run – auto"
            config_id = cfg_dao.get_or_create_config(label=label, settings=self.settings)
            ctx.register("config_id", config_id)
            self.logger.info(f"🧾 Config snapshot ready: config_id={config_id}, label={label}")
        except Exception as e:
            self.logger.error(f"❌ Failed to get/create config_version: {e}", exc_info=True)
            ctx.register("config_id", None)
        try:
            config_id = ctx.get("config_id")

            if config_id is None:
                raise RuntimeError("config_id is None; cannot create/resume run session")

            run_session_manager = ctx.get("run_session_manager")
            run_id = run_session_manager.start_or_resume_run(
                config_id=config_id,
                run_label=label
            )

            ctx.register("run_id", run_id)
            self.logger.info(f"🏃 Active run session ready: run_id={run_id}")

        except Exception as e:
            self.logger.error(f"❌ Failed to create/resume run session: {e}", exc_info=True)
            ctx.register("run_id", None) 
        
        #reset trades based on lrun id
        used_count = ctx.get("trade_dao").count_trade_slots_used(run_id)

        trade_counter = ctx.get("trade_counter")
        trade_counter.reset(used_count)

        self.logger.info(
            f"🔢 Restored trade counter for run_id={run_id}: "
            f"{used_count}/{self.settings['MAXIMUM_TRADES']}"
        )
        
        # 6. Core logic
        ctx.register("trade_lifecycle_service", TradeLifecycleService(ctx))
        ctx.register("trade_enrichment_service", TradeEnrichmentService(ctx))
        ctx.register("token_discovery_persistence_service", TokenDiscoveryPersistenceService(ctx))
        ctx.register("trader", TraderManager(ctx))
        ctx.register("solana_manager", SolanaManager(ctx))
        ctx.register("transaction_manager", TransactionManager(ctx))
        ctx.register("open_position_tracker", OpenPositionTracker(ctx))


        self.tracker = ctx.get("open_position_tracker")
        self.transaction_handler = ctx.get("transaction_manager")
        self.notification_manager = ctx.get("notification_manager")
        self.trade_counter = ctx.get("trade_counter")

        self.logger.info("✅ BotOrchestrator wiring complete")
 
        # Stop flags
        self.stops = {
            "ws": threading.Event(),
            "fetcher": threading.Event(),
            "tracker": threading.Event(),}


        
        # Core components
        self.helius_connector = HeliusConnector(
            ctx=ctx,
            stop_ws=self.stops["ws"],
        )

        self.threads: list[threading.Thread] = []
        
    def _safe_run(self, target, name, stop_event=None, pass_stop_event=False, *args):
        def wrapper():
            while not (stop_event and stop_event.is_set()):
                try:
                    self.logger.info(f"▶️ Starting thread: {name}")

                    if pass_stop_event:
                        target(stop_event, *args)
                    else:
                        target(*args)

                    if stop_event and stop_event.is_set():
                        break

                    self.logger.warning(f"⚠️ Thread {name} exited normally; restarting in 2s")

                except Exception as e:
                    if stop_event and stop_event.is_set():
                        break

                    self.logger.error(f"❌ Thread {name} crashed: {e}", exc_info=True)

                time.sleep(2)

            self.logger.info(f"🛑 Thread {name} stopped.")

        t = threading.Thread(target=wrapper, daemon=True, name=name)
        t.start()
        self.threads.append(t)

    def start(self):
        self._safe_run(
            self.helius_connector.start_ws,
            "WebSocket",
            self.stops["ws"],
            pass_stop_event=False
        )

        self._safe_run(
            self.transaction_handler.run,
            "TxHandler",
            self.stops["fetcher"],
            pass_stop_event=True
        )

        self._safe_run(
            self.tracker.track_positions,
            "Tracker",
            self.stops["tracker"],
            pass_stop_event=True
        )

        self.notification_manager.start()

        self.logger.info("🚀 Bot started with all components")

    def run_cli_loop(self):
        """Blocking CLI watcher until trades complete."""
        max_trades_handled = False

        while True:
            time.sleep(5)

            if self.trade_counter.reached_limit() and not max_trades_handled:
                max_trades_handled = True

                self.logger.warning("🚫 MAX TRADES hit — stopping new trade detection.")

                self.stops["ws"].set()
                self.stops["fetcher"].set()

                try:
                    self.helius_connector.close()
                except Exception as e:
                    self.logger.warning(f"⚠️ Failed to close WebSocket after max trades: {e}")

            if max_trades_handled:
                if self.tracker.has_open_positions():
                    self.logger.info("📊 Waiting for open positions to close before shutdown.")
                    continue

                self.logger.info("✅ Max trades reached and no open positions left — shutting down.")
                try:
                    self.ctx.get("run_session_manager").mark_max_trades_done()
                except Exception as e:
                    self.logger.warning(
                        f"⚠️ Failed to mark run as MAX_TRADES_DONE: {e}",exc_info=True)
                self.shutdown()
                break

    def shutdown(self):
        if getattr(self, "shutdown_started", False):
            return
        self.shutdown_started = True
        
        """Graceful shutdown of trading threads and notifiers."""
        # 1. Stop all loops
        for stop in self.stops.values():
            stop.set()

        # 2. Close WS
        try:
            if hasattr(self, "helius_connector"):
                self.helius_connector.close()
        except Exception as e:
            self.logger.warning(f"⚠️ Failed to close WebSocket: {e}")

        # 3. Stop notifier
        try:
            self.notification_manager.shutdown()
        except Exception as e:
            self.logger.warning(f"⚠️ Notifier shutdown failed: {e}")

        # 4. Join worker threads
        for t in self.threads:
            if t.is_alive():
                t.join(timeout=2)

        self.logger.info("🛑 Bot fully shutdown.")
    