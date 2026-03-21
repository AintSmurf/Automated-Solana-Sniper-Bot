import time
from datetime import datetime, timezone
from services.bot_context import BotContext
from helpers.framework_utils import get_formatted_date_str




class OpenPositionTracker:
    def __init__(self, ctx: BotContext):
        self.ctx = ctx
        self.settings = ctx.settings
        self.logger = ctx.get("logger")
        self.tracker_logger = ctx.get("tracker_logger")
        self.trade_dao = ctx.get("trade_dao")
        self.trader = ctx.get("trader")
        self.notifier = ctx.get("notification_manager")
        self.price_sample_recorder = ctx.get("price_sample_recorder")
        self.jupiter = ctx.get("jupiter_client")
        self.helius = ctx.get("helius_client")
        self.wallet_client = ctx.get("wallet_client")
        self.signatures_dao = ctx.get("signatures_dao")
        self.token_dao = ctx.get("token_dao")
        self.trade_counter = ctx.get("trade_counter")
        self.trade_lifecycle = ctx.get("trade_lifecycle_service")
        self.config_id = ctx.get("config_id")
        self.wallet_reconciliation = ctx.get("wallet_reconciliation_service")        
        self.active_trades = ctx.get("active_trades")
        self.tokens_lock = ctx.get("active_trades_lock")
        self.peak_price_dict = {}
        self.sync_interval = 30 
        self.reconcile_interval = 45
        self.last_reconcile = 0
        self.last_sync = 0

        self.base_token = "So11111111111111111111111111111111111111112"

        self.exit_checks = {"USE_SL": self.check_emergency_sl,"USE_TP": self.check_take_profit,"USE_TSL": self.check_trailing_stop,"USE_TIMEOUT": self.check_timeout,}

    def track_positions(self, stop_event):
        self.logger.info("📊 Starting DB-aware OpenPositionTracker...")

        while not stop_event.is_set():
            try:
                now = time.time()
                if now - self.last_reconcile > self.reconcile_interval:
                    self.wallet_reconciliation.reconcile()
                    self.last_reconcile = now
                if now - self.last_sync > self.sync_interval:
                    self._sync_from_db()
                    self.last_sync = now

                if not self.active_trades:
                    time.sleep(1)
                    continue

                self._evaluate_trades()

            except Exception as e:
                self.logger.error(f"❌ Error in OpenPositionTracker: {e}", exc_info=True)

            time.sleep(3)

    def _sync_from_db(self):
        try:
            sim_mode = self.settings["SIM_MODE"]
            open_trades = self.trade_dao.get_live_trades(sim_mode)
            db_map = {t["token_address"]: t for t in open_trades}
            with self.tokens_lock:
                for token_mint, trade in db_map.items():
                    self.active_trades[token_mint] = dict(trade)
                stale = []
                for token_mint, trade in self.active_trades.items():
                    status = str(trade.get("status", "")).upper()
                    if token_mint not in db_map and status in ("CLOSED",):
                        stale.append(token_mint)

                for token_mint in stale:
                    self.active_trades.pop(token_mint, None)

                self.logger.debug(f"🔄 Synced {len(open_trades)} live trades from DB.")
        except Exception as e:
            self.logger.error(f"❌ Failed DB sync: {e}", exc_info=True)

    def _evaluate_trades(self):
        exit_rules = self.settings.get("EXIT_RULES", {})
        active_trades_snapshot = {}
        with self.tokens_lock:
            tokens = list(self.active_trades.keys())
            active_trades_snapshot = dict(self.active_trades)
        for token_mint in tokens:
            trade = active_trades_snapshot.get(token_mint)
            if not trade:
                continue
            try:
                if token_mint == self.base_token or token_mint == "SOL":
                    continue
                data = self.helius.get_token_meta_data(token_mint)
                token_image = data["image"]
                token_name = data["name"]
                entry_usd = float(trade["entry_usd"])
                current_price_usd = self.jupiter.get_token_price(token_mint)
                pnl = ((current_price_usd - entry_usd) / entry_usd) * 100
                self.price_sample_recorder.maybe_record(token_mint, trade, current_price_usd, pnl)
                self.tracker_logger.info({"event": "track","timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),"token_mint": token_mint,"entry_price": entry_usd,"current_price": current_price_usd,"pnl": pnl,"token_image":token_image,"token_name":token_name})         
                status = str(trade.get("status","")).upper()
                if status == "EXIT_REQUESTED":
                    self._handle_exit(token_mint, trade, current_price_usd, pnl, trigger=trade.get("trigger_reason") or "MANUAL")
                    continue
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
        sim_mode = self.settings["SIM_MODE"]
        if sim_mode:
            sim_sig = f"SIMULATED_SELL_{get_formatted_date_str()}"
            self.signatures_dao.upsert_sell_signature(trade["token_id"], sim_sig)
            self.trade_dao.close_trade(trade_id=trade["id"],exit_usd=current_price_usd,pnl_percent=pnl,trigger_reason=trigger,)
            self.tracker_logger.info({"event": "sell","token_mint": token_mint,"trigger": trigger,"pnl": pnl,"exit_usd": current_price_usd,"simulated": True,})
            self.notifier.notify_text(
                f"⚡ **Exit Triggered (SIM)** — `{token_mint}`\n"
                f"📈 Reason: {trigger}\n"
                f"💵 Current USD: {current_price_usd:.6f}\n"
                f"📊 PnL: {pnl:.2f}%"
            )
            self.logger.info(
                f"🧪 Simulated sell closure for {token_mint} — "
                f"PnL: {pnl:.2f}% | Exit USD: {current_price_usd:.8f}"
            )

            with self.tokens_lock:
                self.active_trades.pop(token_mint, None)
            return
        sig = self.trader.sell(token_mint, self.base_token, trigger_reason=trigger)
        self.tracker_logger.info({"event": "sell", "token_mint": token_mint})

        if not sig:
            self.logger.warning(f"⚠️ Real SELL failed for {token_mint}, keeping trade open.")

    def manual_close(self, token_mint: str,trigger = "MANUAL") -> bool:
        try:
            with self.tokens_lock:
                trade = self.active_trades.get(token_mint)
            if not trade:
                self.logger.warning(f"⚠️ Tried to manually close {token_mint}, but it's not active.")
                return False
            sim_mode = self.settings["SIM_MODE"]
            entry_usd = float(trade.get("entry_usd", 0) or 0)

            current_price_usd = self.jupiter.get_token_price(token_mint)
            
            pnl = 0.0
            if current_price_usd is not None and current_price_usd > 0 and entry_usd:
                pnl = ((current_price_usd - entry_usd) / entry_usd) * 100

            if sim_mode:
                sim_sig = f"SIMULATED_MANUAL_{get_formatted_date_str()}"
                try:
                    self.signatures_dao.upsert_sell_signature(trade["token_id"], sim_sig)
                except Exception as e:
                    self.logger.warning(f"⚠️ Failed to update simulated manual sell signature for {token_mint}: {e}")
                self.trade_dao.close_trade(trade_id=trade["id"],exit_usd=current_price_usd,pnl_percent=pnl,trigger_reason=trigger)
                self.logger.info(f"🧪 Manual simulated closure for {token_mint} — "f"PnL: {pnl:.2f}% | Exit USD: {current_price_usd:.6f}" )
                with self.tokens_lock:
                    self.active_trades.pop(token_mint, None)
                return True
            try:
                return self.trade_lifecycle.request_exit(token_mint, trigger)
            except Exception as e:
                self.logger.warning(f"⚠️ Failed to mark SELLING/trigger for {token_mint}: {e}")
        except Exception as e:
            self.logger.error(f"❌ Manual close failed for {token_mint}: {e}", exc_info=True)
            return False

    def has_open_positions(self):
        if self.trader and self.trader.has_pending_trades():
            return True
        try:
            with self.tokens_lock:
                for trade in self.active_trades.values():
                    status = str(trade.get("status"))
                    if status in ("SUBMITTED","CONFIRMED","FINALIZED","SELLING","SELL_TIMEOUT","SIMULATED","RECOVERED","EXIT_REQUESTED"):
                        return True
            live_trades = self.trade_dao.get_live_trades(self.settings["SIM_MODE"])
            return len(live_trades) > 0

        except Exception as e:
            self.logger.error(f"⚠️ has_open_positions failed: {e}", exc_info=True)
        return False

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
        sl_pct = self.settings.get("SL", 0.1)
        early_pct = self.settings.get("EARLY_SL_PCT", 0.10)
        early_seconds = self.settings.get("EARLY_SL_SECONDS", 30)

        peak = self.peak_price_dict.get(token_mint, buy_usd)
        min_tsl_mult = self.settings.get("MIN_TSL_TRIGGER_MULTIPLIER", 1.3)
        has_pumped = peak >= buy_usd * min_tsl_mult
        if has_pumped:
            return None
        seconds_since = None
        try:
            buy_time = trade.get("trade_time")
            if isinstance(buy_time, datetime):
                if buy_time.tzinfo is None:
                    buy_time = buy_time.replace(tzinfo=timezone.utc)
                now = datetime.now(timezone.utc)
                seconds_since = (now - buy_time).total_seconds()
        except Exception as e:
            self.logger.warning(f"⚠️ SL time calc failed for {token_mint}: {e}")
        if not buy_usd:
            return None
        price_ratio = curr_usd / buy_usd
        if (
            seconds_since is not None
            and seconds_since >= early_seconds
            and price_ratio <= (1.0 - early_pct) 
        ):
            return {"trigger": "EARLY_STOP"}
        if price_ratio <= (1.0 - sl_pct):         
            return {"trigger": "SL"}

        return None

    def check_timeout(self, token_mint, buy_usd, curr_usd, trade):
        timeout = self.settings.get("TIMEOUT_SECONDS", 300)
        threshold = self.settings.get("TIMEOUT_PROFIT_THRESHOLD", 1.2)
        pnl_floor = self.settings.get("TIMEOUT_PNL_FLOOR", -0.03)  # e.g. -3%

        try:
            buy_time = trade.get("trade_time")
            if isinstance(buy_time, datetime):
                if buy_time.tzinfo is None:
                    buy_time = buy_time.replace(tzinfo=timezone.utc)
                now = datetime.now(timezone.utc)
                seconds_since = (now - buy_time).total_seconds()
            else:
                seconds_since = 0

            if not buy_usd:
                return None
            price_ratio = curr_usd / buy_usd
            pnl_frac = price_ratio - 1.0
            if (
                seconds_since > timeout
                and curr_usd < buy_usd * threshold
                and pnl_frac >= pnl_floor
            ):
                return {"trigger": "TIMEOUT"}

        except Exception as e:
            self.logger.warning(f"⚠️ Timeout check failed for {token_mint}: {e}")

        return None

