import time
from datetime import datetime, timezone
import threading
from services.bot_context import BotContext
from helpers.framework_utils import get_formatted_date_str,unique_recovery_sig
from config.dex_detection_rules import KNOWN_TOKENS




class OpenPositionTracker:
    def __init__(self, ctx: BotContext):
        self.ctx = ctx
        self.settings = ctx.settings
        self.logger = ctx.get("logger")
        self.tracker_logger = ctx.get("tracker_logger")
        self.trade_dao = ctx.get("trade_dao")
        self.trader = ctx.get("trader")
        self.notifier = ctx.get("notification_manager")

        self.active_trades = {}
        self.peak_price_dict = {}
        self.buy_timestamp = {}
        self.sync_interval = 30 
        self.reconcile_interval = 120 
        self.last_reconcile = 0
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
                if now - self.last_reconcile > self.reconcile_interval:
                    self._reconcile_wallet_with_db()
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
            open_trades = self.trade_dao.get_open_trades(sim_mode)
            with self.tokens_lock:
                self.active_trades = {t["token_address"]: t for t in open_trades}
            self.logger.debug(f"🔄 Synced {len(open_trades)} {'SIMULATED' if sim_mode else 'REAL'} trades from DB.")
        except Exception as e:
            self.logger.error(f"❌ Failed DB sync: {e}", exc_info=True)

    def _evaluate_trades(self):
        jup = self.ctx.get("jupiter_client")
        hel = self.ctx.get("helius_client")
        exit_rules = self.settings.get("EXIT_RULES", {})
        with self.tokens_lock:
            tokens = list(self.active_trades.keys())

        for token_mint in tokens:
            trade = self.active_trades.get(token_mint)
            if not trade:
                continue

            try:
                if token_mint == self.base_token or token_mint == "SOL":
                    continue
                data = hel.get_token_meta_data(token_mint)
                token_image = data["image"]
                token_name = data["name"]
                entry_usd = float(trade["entry_usd"])
                current_price_usd = jup.get_token_price(token_mint)
                pnl = ((current_price_usd - entry_usd) / entry_usd) * 100

                self.tracker_logger.info({
                    "event": "track",
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "token_mint": token_mint,
                    "entry_price": entry_usd,
                    "current_price": current_price_usd,
                    "pnl": pnl,
                    "token_image":token_image,
                    "token_name":token_name
                })

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
        trade_dao = self.ctx.get("trade_dao")
        sig_dao = self.ctx.get("signatures_dao")
        sim_mode = self.settings["SIM_MODE"]
        if sim_mode:
            sim_sig = f"SIMULATED_SELL_{get_formatted_date_str()}"
            sig_dao.update_sell_signature(trade["token_id"], sim_sig)
            trade_dao.close_trade(
                trade_id=trade["id"],
                exit_usd=current_price_usd,
                pnl_percent=pnl,
                trigger_reason=trigger,
            )
            self.tracker_logger.info({
                "event": "sell",
                "token_mint": token_mint,
                "trigger": trigger,
                "pnl": pnl,
                "exit_usd": current_price_usd,
                "simulated": True,
            })

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
            entry_usd = float(trade.get("entry_usd", 0) or 0)
            jup = self.ctx.get("jupiter_client")

            current_price_usd = jup.get_token_price(token_mint)
            pnl = ((current_price_usd - entry_usd) / entry_usd) * 100 if entry_usd else 0.0

            trade_dao = self.ctx.get("trade_dao")
            sig_dao = self.ctx.get("signatures_dao")
            sim_mode = self.settings["SIM_MODE"]
            if sim_mode:
                sim_sig = f"SIMULATED_MANUAL_{get_formatted_date_str()}"
                try:
                    sig_dao.update_sell_signature(trade["token_id"], sim_sig)
                except Exception as e:
                    self.logger.warning(
                        f"⚠️ Failed to update simulated manual sell signature for {token_mint}: {e}"
                    )

                trade_dao.close_trade(
                    trade_id=trade["id"],
                    exit_usd=current_price_usd,
                    pnl_percent=pnl,
                    trigger_reason=trigger,
                )
                self.logger.info(
                    f"🧪 Manual simulated closure for {token_mint} — "
                    f"PnL: {pnl:.2f}% | Exit USD: {current_price_usd:.6f}"
                )
            else:
                sig = self.trader.sell(token_mint, self.base_token, trigger_reason=trigger)

                if not sig:
                    self.logger.warning(
                        f"⚠️ Manual real SELL failed for {token_mint}, keeping trade open."
                    )
                    return False

                sig_dao.update_sell_signature(trade["token_id"], sig)
                trade_dao.close_trade(
                    trade_id=trade["id"],
                    exit_usd=current_price_usd,
                    pnl_percent=pnl,
                    trigger_reason=trigger,
                )
                self.logger.info(
                    f"✅ Manual real closure for {token_mint} — TX: {sig} | "
                    f"PnL: {pnl:.2f}% | Exit USD: {current_price_usd:.6f}"
                )
            with self.tokens_lock:
                self.active_trades.pop(token_mint, None)

            self.tracker_logger.info({
                "event": "sell",
                "token_mint": token_mint,
                "trigger": trigger,
                "pnl": pnl,
                "exit_usd": current_price_usd,
                "simulated": True,
            })
            return True

        except Exception as e:
            self.logger.error(f"❌ Manual close failed for {token_mint}: {e}", exc_info=True)
            return False

    def has_open_positions(self):
        trader = self.ctx.get("trader")
        if trader and trader.has_pending_trades():
            return True
        try:
            with self.tokens_lock:
                for trade in self.active_trades.values():
                    status = str(trade.get("status"))
                    if status in ("FINALIZED", "SELLING", "SIMULATED"):
                        return True
            live_trades = self.trade_dao.get_live_trades(self.settings["SIM_MODE"])
            return len(live_trades) > 0

        except Exception as e:
            self.logger.error(f"⚠️ has_open_positions failed: {e}", exc_info=True)
            return False

    def _reconcile_wallet_with_db(self):
        try:
            wallet = self.ctx.get("wallet_client")
            trade_dao = self.ctx.get("trade_dao")
            sig_dao = self.ctx.get("signatures_dao")
            token_dao = self.ctx.get("token_dao")
            sim_mode = self.settings["SIM_MODE"]
            dust_threshold_usd = self.ctx.settings["DUST_THRESHOLD_USD"]

            if sim_mode:
                return

            IGNORED_MINTS = set(KNOWN_TOKENS.values())
            self.logger.debug(f"Ignoring known base tokens: {', '.join(KNOWN_TOKENS.keys())}")
            with self.tokens_lock:
                active_trades = dict(self.active_trades)
            wallet_balances = wallet.get_token_balances()
            wallet_tokens: dict[str, float] = {}
            price_cache: dict[str, float] = {}

            for b in wallet_balances:
                token_mint = b["token_mint"]
                balance = float(b["balance"])

                if token_mint in IGNORED_MINTS:
                    continue

                if token_mint not in price_cache:
                    try:
                        price_cache[token_mint] = self.ctx.get("jupiter_client").get_token_price(token_mint)
                    except Exception as e:
                        self.logger.warning(f"Failed to fetch price for {token_mint}: {e}")
                        price_cache[token_mint] = 0.0

                usd_price = price_cache[token_mint]
                usd_value = balance * usd_price
                if usd_value < dust_threshold_usd:
                    self.logger.info(
                        f"Ignoring dust token {token_mint} — {balance:.8f} worth ${usd_value:.6f}"
                    )
                    continue

                wallet_tokens[token_mint] = balance
            open_trades = trade_dao.get_open_trades(sim_mode)
            db_tokens = {t["token_address"]: t for t in open_trades}
            for token_mint, bal in wallet_tokens.items():
                if token_mint in active_trades:
                    self.logger.debug(f"⏩ Token {token_mint} already active, skipping recovery.")
                    continue

                if bal > 0 and token_mint not in db_tokens:
                    self.notifier.notify_text(
                        f"🩹 **Recovered Token** — `{token_mint}` added to DB\n"
                        f"💰 Balance: {bal:.6f}"
                    )
                    self.logger.warning(
                        f"🩹 Found token in wallet but not DB: {token_mint} (balance={bal}) — creating recovery trade"
                    )
                    entry_usd = price_cache.get(token_mint)
                    token_id = token_dao.get_or_create_token(token_mint, None)
                    trade_id = trade_dao.insert_trade(
                        token_id=token_id,
                        trade_type="BUY",
                        entry_usd=entry_usd,
                        simulation=sim_mode,
                        status="RECOVERED",
                    )
                    sig_dao.insert_signature(token_id, buy_signature=unique_recovery_sig())
                    trade = trade_dao.get_trade_by_id(trade_id)
                    with self.tokens_lock:
                        self.active_trades[token_mint] = trade

            for token_mint, trade in db_tokens.items():
                if token_mint in IGNORED_MINTS:
                    continue
                if token_mint in active_trades:
                    self.logger.debug(
                        f"⏩ Token {token_mint} is active (status={trade.get('status')}), skipping LOST reconciliation."
                    )
                    continue
                if str(trade.get("status")) == "SELLING":
                    self.logger.debug(f"⏳ Token {token_mint} in SELLING status, waiting for normal close.")
                    continue

                if token_mint not in wallet_tokens:
                    self.notifier.notify_text(
                        f"🧹 **Lost Token** — `{token_mint}` removed (no longer in wallet)"
                    )
                    self.logger.warning(
                        f"🧹 Token missing in wallet but open in DB: {token_mint} — closing trade as 'LOST'"
                    )
                    trade_dao.close_trade(
                        trade_id=trade["id"],
                        exit_usd=0.0,
                        pnl_percent=-100.0,
                        trigger_reason="LOST",
                    )
                    with self.tokens_lock:
                        self.active_trades.pop(token_mint, None)

            self.logger.info(
                f"🔍 Reconciliation complete — Wallet={len(wallet_tokens)}, DB={len(db_tokens)}"
            )

        except Exception as e:
            self.logger.error(f"❌ Wallet↔DB reconciliation failed: {e}", exc_info=True)

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
            buy_time = trade.get("timestamp")
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
            buy_time = trade.get("timestamp")
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

