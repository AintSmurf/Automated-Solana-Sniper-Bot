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
        
        
        self.last_price_sample: dict[str, float] = {}
        self.price_sample_interval = 15
        self.active_trades = {}
        self.peak_price_dict = {}
        self.buy_timestamp = {}
        self.sync_interval = 30 
        self.reconcile_interval = 45
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
            open_trades = self.trade_dao.get_live_trades(sim_mode)
            with self.tokens_lock:
                self.active_trades = {t["token_address"]: t for t in open_trades}
            self.logger.debug(f"🔄 Synced {len(open_trades)} {'SIMULATED' if sim_mode else 'REAL'} trades from DB.")
        except Exception as e:
            self.logger.error(f"❌ Failed DB sync: {e}", exc_info=True)

    def _evaluate_trades(self):
        jup = self.ctx.get("jupiter_client")
        hel = self.ctx.get("helius_client")
        price_sample_dao = self.ctx.get("price_sample_dao")
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
                now = time.time()
                last_ts = self.last_price_sample.get(token_mint, 0)

                if now - last_ts >= self.price_sample_interval:
                    try:
                        price_sample_dao.insert_sample(
                            trade_id=trade["id"],
                            token_id=trade["token_id"],
                            price_usd=current_price_usd,
                            pnl_percent=pnl,
                        )
                        self.last_price_sample[token_mint] = now
                    except Exception as e:
                        self.logger.warning(f"⚠️ Failed to insert price sample for {token_mint}: {e}")

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
        trade_dao = self.ctx.get("trade_dao")
        sig_dao = self.ctx.get("signatures_dao")
        sim_mode = self.settings["SIM_MODE"]
        if sim_mode:
            sim_sig = f"SIMULATED_SELL_{get_formatted_date_str()}"
            sig_dao.upsert_sell_signature(trade["token_id"], sim_sig)
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
            trade_dao = self.ctx.get("trade_dao")
            sig_dao = self.ctx.get("signatures_dao")
            sim_mode = self.settings["SIM_MODE"]
            entry_usd = float(trade.get("entry_usd", 0) or 0)
            jup = self.ctx.get("jupiter_client")

            current_price_usd = jup.get_token_price(token_mint)
            
            pnl = 0.0
            if current_price_usd is not None and current_price_usd > 0 and entry_usd:
                pnl = ((current_price_usd - entry_usd) / entry_usd) * 100

            if sim_mode:
                sim_sig = f"SIMULATED_MANUAL_{get_formatted_date_str()}"
                try:
                    sig_dao.upsert_sell_signature(trade["token_id"], sim_sig)
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
                self.logger.info(f"🧪 Manual simulated closure for {token_mint} — "f"PnL: {pnl:.2f}% | Exit USD: {current_price_usd:.6f}" )
                return True
            try:
                trade_dao.update_trade_status(trade["id"], "EXIT_REQUESTED")
                trade_dao.update_exit_data(trade["id"], trigger)
                with self.tokens_lock:
                    if token_mint in self.active_trades:
                        self.active_trades[token_mint]["status"] = "EXIT_REQUESTED"
                        self.active_trades[token_mint]["trigger_reason"] = trigger
                return True
            except Exception as e:
                self.logger.warning(f"⚠️ Failed to mark SELLING/trigger for {token_mint}: {e}")
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
                    if status in ("SUBMITTED","CONFIRMED","FINALIZED","SELLING","SELL_TIMEOUT","SIMULATED","RECOVERED","EXIT_REQUESTED"):
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
            config_id = self.ctx.get("config_id")

            if sim_mode:
                return

            IGNORED_MINTS = set(KNOWN_TOKENS.values())
            self.logger.debug(f"Ignoring known base tokens: {', '.join(KNOWN_TOKENS.keys())}")
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
                        price_cache[token_mint] = self.ctx.get("jupiter_client").get_token_price(token_mint) or 0.0
                    except Exception as e:
                        self.logger.warning(f"Failed to fetch price for {token_mint}: {e}")
                        price_cache[token_mint] = 0.0

                usd_price = float(price_cache[token_mint] or 0.0)
                usd_value = balance * usd_price

                if usd_value < dust_threshold_usd:
                    continue

                wallet_tokens[token_mint] = balance

            submitted = trade_dao.get_submitted_trades(sim_mode)
            live = trade_dao.get_live_trades(sim_mode)
            try:
                selling = trade_dao.get_selling_trades(sim_mode)
            except Exception:
                selling = []

            open_trades = submitted + live + selling

            db_tokens: dict[str, dict] = {}
            for t in open_trades:
                addr = t.get("token_address")
                if addr and addr not in db_tokens:
                    db_tokens[addr] = t
            for token_mint, bal in wallet_tokens.items():
                if token_mint in IGNORED_MINTS:
                    continue
                if token_mint in db_tokens:
                    db_trade = db_tokens[token_mint]
                    status = str(db_trade.get("status", "")).upper()

                    with self.tokens_lock:
                        self.active_trades[token_mint] = db_trade
                    if status in ("SUBMITTED", "CONFIRMED", "BUY_FAILED", "BUY_TIMEOUT"):
                        try:
                            trade_dao.update_trade_status_with_ts(db_trade["id"], "FINALIZED")
                            with self.tokens_lock:
                                if token_mint in self.active_trades:
                                    self.active_trades[token_mint]["status"] = "FINALIZED"
                                    try:
                                        self.ctx.get("trade_counter").increment()
                                    except Exception:
                                        pass
                            self.logger.warning(f"🩹 Reconcile repaired {status} -> FINALIZED via WALLET for {token_mint}")
                        except Exception as e:
                            self.logger.warning(f"⚠️ Failed to repair status -> FINALIZED for {token_mint}: {e}")
                        try:
                            buy_sig = sig_dao.get_buy_signature(db_trade["token_id"])
                            if not buy_sig:
                                sig_dao.upsert_buy_signature(db_trade["token_id"], unique_recovery_sig())
                        except Exception:
                            pass
                    continue
                if bal > 0:
                    latest = trade_dao.get_latest_trade_by_token_any_status(token_mint)
                    if latest:
                        latest_status = str(latest.get("status", "")).upper()
                        latest_reason = str(latest.get("trigger_reason", "")).upper()

                        if latest_status == "CLOSED" and latest_reason == "WALLET_MISSING":
                            closed_at = latest.get("closed_at")
                            if isinstance(closed_at, datetime) and closed_at.tzinfo is None:
                                closed_at = closed_at.replace(tzinfo=timezone.utc)

                            if closed_at and (datetime.now(timezone.utc) - closed_at).total_seconds() < 300:
                                trade_dao.reopen_trade(latest["id"], status="FINALIZED")
                                revived = trade_dao.get_trade_by_id(latest["id"])

                                with self.tokens_lock:
                                    self.active_trades[token_mint] = revived

                                self.logger.warning(f"🩹 Revived WALLET_MISSING -> FINALIZED for {token_mint}")
                                continue

                    self.notifier.notify_text(
                        f"🩹 **Recovered Token** — `{token_mint}` added to DB\n💰 Balance: {bal:.6f}"
                    )
                    self.logger.warning(
                        f"🩹 Found token in wallet but not DB: {token_mint} (balance={bal}) — creating recovery trade"
                    )

                    entry_usd = float(price_cache.get(token_mint) or 0.0)
                    token_id = token_dao.get_or_create_token(token_mint, None)

                    trade_id = trade_dao.insert_trade(
                        token_id=token_id,
                        trade_type="BUY",
                        entry_usd=entry_usd,
                        simulation=sim_mode,
                        status="RECOVERED",
                        config_id=config_id,
                    )
                    sig_dao.upsert_buy_signature(token_id, buy_signature=unique_recovery_sig())
                    trade = trade_dao.get_trade_by_id(trade_id)

                    with self.tokens_lock:
                        self.ctx.get("trade_counter").increment()
                        self.active_trades[token_mint] = trade
            for token_mint, trade in db_tokens.items():
                if token_mint in IGNORED_MINTS:
                    continue
                status = str(trade.get("status", "")).upper()
                if status in ("SUBMITTED", "CONFIRMED", "SELLING", "SELL_TIMEOUT","EXIT_REQUESTED"):
                    continue
                if token_mint not in wallet_tokens:
                    self.notifier.notify_text(
                        f"🧹 **Wallet Missing Token** — `{token_mint}` closing as LOST"
                    )
                    self.logger.warning(
                        f"🧹 Token missing in wallet but open in DB: {token_mint} — closing trade as WALLET_MISSING"
                    )

                    try:
                        trade_dao.close_trade(
                            trade_id=trade["id"],
                            exit_usd=0.0,
                            pnl_percent=-100.0,
                            trigger_reason="WALLET_MISSING",
                        )
                    except Exception as e:
                        self.logger.warning(f"⚠️ Failed to close WALLET_MISSING for {token_mint}: {e}")

                    with self.tokens_lock:
                        self.active_trades.pop(token_mint, None)

            self.logger.info(
                f"🔍 Reconciliation complete — Wallet={len(wallet_tokens)}, DB(open-ish)={len(db_tokens)}"
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

