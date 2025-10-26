import time
from datetime import datetime, timezone
import threading
from services.bot_context import BotContext




class OpenPositionTracker:
    def __init__(self, ctx: BotContext):
        self.ctx = ctx
        self.settings = ctx.settings
        self.logger = ctx.get("logger")
        self.tracker_logger = ctx.get("tracker_logger")
        self.trade_dao = ctx.get("trade_dao")
        self.trader = ctx.get("trader")

        self.active_trades = {}
        self.peak_price_dict = {}
        self.buy_timestamp = {}
        self.sync_interval = 30 
        self.last_sync = 0

        self.base_token = "So11111111111111111111111111111111111111112"
        self.tokens_lock = threading.Lock()

        self.exit_checks = {
            "USE_SL": self.check_emergency_sl,
            "USE_TP": self.check_take_profit,
            "USE_TSL": self.check_trailing_stop,
            "USE_TIMEOUT": self.check_timeout,
        }

    def track_positions(self, stop_event):
        self.logger.info("📊 Starting DB-aware OpenPositionTracker...")

        while not stop_event.is_set():
            try:
                now = time.time()
                if now - self.last_sync > self.sync_interval:
                    self._sync_from_db()
                    self.last_sync = now

                if not self.active_trades:
                    time.sleep(1)
                    continue

                self._evaluate_trades()

            except Exception as e:
                self.logger.error(f"❌ Error in OpenPositionTracker: {e}", exc_info=True)

            time.sleep(1)

    def _sync_from_db(self):
        try:
            sim_mode = self.settings["SIM_MODE"]
            open_trades = self.trade_dao.get_open_trades(sim_mode)
            with self.tokens_lock:
                self.active_trades = {t["token_address"]: t for t in open_trades}
            self.logger.debug(f"🔄 Synced {len(open_trades)} {'SIMULATED' if sim_mode else 'REAL'} trades from DB.")
        except Exception as e:
            self.logger.error(f"❌ Failed DB sync: {e}", exc_info=True)

    def _evaluate_trades(self):
        """Check current prices and exit triggers."""
        jup = self.ctx.get("jupiter_client")
        exit_rules = self.settings.get("EXIT_RULES", {})

        with self.tokens_lock:
            tokens = list(self.active_trades.keys())

        for token_mint in tokens:
            trade = self.active_trades.get(token_mint)
            if not trade:
                continue

            try:
                entry_usd = float(trade["entry_usd"])
                current_price_usd = jup.get_token_price(token_mint)
                pnl = ((current_price_usd - entry_usd) / entry_usd) * 100

                self.tracker_logger.info({
                    "event": "track",
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "token_mint": token_mint,
                    "entry_usd": entry_usd,
                    "current_price": current_price_usd,
                    "pnl": pnl,
                })

                # Apply exit checks
                for rule, func in self.exit_checks.items():
                    if exit_rules.get(rule, False):
                        result = func(token_mint, entry_usd, current_price_usd, trade)
                        if result:
                            trigger = result["trigger"]
                            self.logger.info(f"⚡ Exit triggered: {trigger} for {token_mint} ({pnl:.2f}%)")
                            self._handle_exit(token_mint, trade, current_price_usd, pnl, trigger)
                            break

            except Exception as e:
                self.logger.warning(f"⚠️ Evaluation error for {token_mint}: {e}")

    def _handle_exit(self, token_mint, trade, current_price_usd, pnl, trigger):
        sig = self.trader.sell(token_mint, self.base_token, trigger_reason=trigger)
        trade_dao = self.ctx.get("trade_dao")
        sig_dao = self.ctx.get("signatures_dao")

        if not sig and self.settings.get("SIM_MODE", False):
            sig = f"SIM-{int(time.time())}"
            sig_dao.update_sell_signature(trade["token_id"], sig)
            trade_dao.close_trade(
                trade_id=trade["id"],
                exit_usd=current_price_usd,
                pnl_percent=pnl,
                trigger_reason=trigger
            )
            self.logger.info(f"🧪 Simulated sell closure for {token_mint} — PnL: {pnl:.2f}% | Exit USD: {current_price_usd:.2f}")
            with self.tokens_lock:
                self.active_trades.pop(token_mint, None)
            return

    def has_open_positions(self):
        with self.tokens_lock:
            return len(self.active_trades) > 0

    def check_take_profit(self, token_mint, buy_usd, curr_usd, trade):
        tp = self.settings.get("TP", 2.0)
        return {"trigger": "TP"} if curr_usd >= buy_usd * tp else None

    def check_trailing_stop(self, token_mint, buy_usd, curr_usd, trade):
        sl = self.settings.get("TRAILING_STOP", 0.2)
        min_trigger = self.settings.get("MIN_TSL_TRIGGER_MULTIPLIER", 1.15)
        peak = self.peak_price_dict.get(token_mint, buy_usd)
        if curr_usd > peak:
            self.peak_price_dict[token_mint] = curr_usd
        if peak >= buy_usd * min_trigger and curr_usd <= peak * (1 - sl):
            return {"trigger": "TSL"}
        return None

    def check_emergency_sl(self, token_mint, buy_usd, curr_usd, trade):
        sl = self.settings.get("SL", 0.1)
        peak = self.peak_price_dict.get(token_mint, buy_usd)
        has_pumped = peak >= buy_usd * self.settings.get("MIN_TSL_TRIGGER_MULTIPLIER", 1.5)
        if not has_pumped and curr_usd <= buy_usd * (1 - sl):
            return {"trigger": "SL"}
        return None

    def check_timeout(self, token_mint, buy_usd, curr_usd, trade):
        timeout = self.settings.get("TIMEOUT_SECONDS", 300)
        threshold = self.settings.get("TIMEOUT_PROFIT_THRESHOLD", 1.2)
        try:
            buy_time = trade.get("timestamp")
            if isinstance(buy_time, datetime):
                if buy_time.tzinfo is None:
                    buy_time = buy_time.replace(tzinfo=timezone.utc)
                now = datetime.now(timezone.utc)
                seconds_since = (now - buy_time).total_seconds()
            else:
                seconds_since = 0

            if seconds_since > timeout and curr_usd < buy_usd * threshold:
                return {"trigger": "TIMEOUT"}
        except Exception as e:
            self.logger.warning(f"⚠️ Timeout check failed for {token_mint}: {e}")
        return None