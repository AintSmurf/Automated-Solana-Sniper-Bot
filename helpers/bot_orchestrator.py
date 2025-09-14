# helpers/bot_orchestrator.py
import threading
import time
from helpers.open_positions import OpenPositionTracker
from helpers.rate_limiter import RateLimiter
from connectors.helius_connector import HeliusConnector
from helpers.logging_manager import LoggingHandler
from notification.manager import NotificationManager
from helpers.trade_counter import TradeCounter
from helpers.volume_tracker import VolumeTracker
import pandas as pd



logger = LoggingHandler.get_logger()


class BotOrchestrator:
    def __init__(self, trade_counter:TradeCounter, settings):
        self.settings = settings
        self.trade_counter  = trade_counter
        self.trade_counter.reset()
        self.volume_tracker = VolumeTracker()



        # Stop flags
        self.stop_ws = threading.Event()
        self.stop_fetcher = threading.Event()
        self.stop_tracker = threading.Event()
        self.stop_retry = threading.Event()

        # Rate limiter
        helius_rl = settings["RATE_LIMITS"]["helius"]
        self.rate_limiter = RateLimiter(
            min_interval=helius_rl["min_interval"],
            jitter_range=helius_rl["jitter_range"],
            max_requests_per_minute=helius_rl["max_requests_per_minute"],
            name=helius_rl["name"],
        )

        # Core components
        self.helius_connector = HeliusConnector(
            rate_limiter=self.rate_limiter,
            trade_counter=trade_counter,
            stop_ws=self.stop_ws,
            stop_fetcher=self.stop_fetcher,
            volume_tracker=self.volume_tracker,
        )
        self.tracker = OpenPositionTracker(rate_limiter=self.rate_limiter)

        # Unified notifier (Discord now; Slack/Telegram later)
        self.notifier = NotificationManager(settings)

        self.threads: list[threading.Thread] = []

    def _safe_run(self, target, name, *args):
        def wrapper():
            while not self.stop_ws.is_set():
                try:
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
        """Start core trading threads + notifier loop thread."""
        self._safe_run(self.helius_connector.start_ws, "WebSocket")
        self._safe_run(self.helius_connector.run_transaction_fetcher, "Fetcher")
        self._safe_run(self.tracker.track_positions, "Tracker", self.stop_tracker)
        self._safe_run(self.tracker.retry_failed_sells, "Retry", self.stop_retry)

        # Start notifications (its own asyncio loop thread)
        self.notifier.start()

        logger.info("🚀 Bot started with all components")

    def run_cli_loop(self):
        """Blocking CLI watcher until trades complete."""
        while True:
            time.sleep(5)

            if  self.trade_counter.reached_limit():
                logger.warning("🚫 MAX TRADES hit — stopping trade threads.")
                self.stop_ws.set()
                self.stop_fetcher.set()
                if not self.tracker.has_open_positions() and not self.tracker.has_failed_sells():
                    logger.info("✅ Trades done — shutting everything down.")
                    self.shutdown()
                    break

    def shutdown(self):
        """Graceful shutdown of trading threads and notifiers."""
        # 1. Stop all loops
        for stop in (self.stop_ws, self.stop_fetcher, self.stop_tracker, self.stop_retry):
            stop.set()

        # 2. Close WS
        try:
            if hasattr(self, "helius_connector"):
                self.helius_connector.close()
        except Exception as e:
            logger.warning(f"⚠️ Failed to close WebSocket: {e}")

        # 3. Stop notifier
        try:
            self.notifier.shutdown()
        except Exception as e:
            logger.warning(f"⚠️ Notifier shutdown failed: {e}")

        # 4. Join worker threads
        for t in self.threads:
            if t.is_alive():
                t.join(timeout=2)

        # 5. Only one place logs shutdown
        logger.info("🛑 Bot fully shutdown.")

    def get_api_stats(self):
        return {
            "helius": self.rate_limiter.get_stats(),
            "jupiter": self.helius_connector.solana_manager.jupiter_rate_limiter.get_stats()
        }
    
    def close_trade(self, token_mint):
        df = pd.read_csv(self.tracker.file_path)
        row = df[df["Token_bought"] == token_mint].iloc[0]

        input_mint = row["Token_sold"]
        executed_price_usd = self.tracker.solana_manager.get_token_price(token_mint)
        mode = self.settings["SIM_MODE"]

        if mode:
            self.tracker.simulated_sell_and_log(token_mint, input_mint, executed_price_usd, trigger="MANUAL_UI")
        else:
            self.tracker.sell_and_update(token_mint, input_mint, trigger="MANUAL_UI")
