from datetime import datetime, timezone
from services.bot_context import BotContext
from helpers.framework_utils import get_formatted_date_str


class TradeLifecycleService:
    def __init__(self, ctx: BotContext):
        self.ctx = ctx
        self.logger = ctx.get("logger")
        self.tracker_logger = ctx.get("tracker_logger")
        self.live_channel = ctx.settings_manager.get_notification_settings()["DISCORD"]["LIVE_CHANNEL"]
        self.active_trades = ctx.get("active_trades")
        self.tokens_lock = ctx.get("active_trades_lock")

    def insert_simulated_trade(self, output_mint: str, real_entry_price: float, entry_price: float):
        """Insert a simulated trade with UTC timestamps for consistency."""
        token_dao = self.ctx.get("token_dao")
        trade_dao = self.ctx.get("trade_dao")
        sig_dao = self.ctx.get("signatures_dao")
        config_id = self.ctx.get("config_id")
        run_id=self.ctx.get("run_id")

        token_id = token_dao.get_or_create_token(output_mint, None)
        now_utc = datetime.now(timezone.utc)

        trade_id = trade_dao.insert_trade(
            token_id,
            "BUY",
            real_entry_price,
            simulation=True,
            status="SIMULATED",
            confirmed_at=now_utc,
            finalized_at=now_utc,
            config_id=config_id,
            run_id = run_id,
        )
        sig_dao.upsert_buy_signature(token_id,f"SIMULATED_BUY_{get_formatted_date_str()}",trade_id)

        trade = trade_dao.get_trade_by_id(trade_id)
        with self.tokens_lock:
            self.active_trades[output_mint] = trade
        self.ctx.get("trade_counter").increment()

        self.logger.debug(f"📡 Added {output_mint} (SIM) to tracker instantly.")
        self.logger.info(f"🧪 Simulated trade created for {output_mint} (trade_id={trade_id})")

        return "SIMULATED"

    def insert_submitted_buy(self, data: dict, buy_signature: str, output_mint: str):
        token_dao = self.ctx.get("token_dao")
        trade_dao = self.ctx.get("trade_dao")
        sig_dao = self.ctx.get("signatures_dao")
        config_id = self.ctx.get("config_id")
        run_id=self.ctx.get("run_id")

        existing = trade_dao.get_latest_trade_by_token_and_statuses(
            output_mint, ("SUBMITTED", "CONFIRMED", "FINALIZED")
        )
        if existing:
            self.logger.debug(f"⏩ Existing open-ish trade for {output_mint} "f"(trade_id={existing['id']}, status={existing.get('status')})")
            sig_dao.upsert_buy_signature(existing["token_id"],buy_signature,existing["id"],)
            return existing["id"]
        token_id = token_dao.get_or_create_token(output_mint, None)
        entry_usd = float(data.get("entry_usd") or 0.0)
        if entry_usd <= 0:
            try:
                entry_usd = float(self.ctx.get("jupiter_client").get_token_price(output_mint) or 0.0)
            except Exception:
                entry_usd = 0.0

        trade_id = trade_dao.insert_trade(
            token_id=token_id,
            trade_type="BUY",
            entry_usd=entry_usd,
            simulation=False,
            status="SUBMITTED",
            confirmed_at=None,
            finalized_at=None,
            config_id=config_id,
            run_id = run_id,
        )
        sig_dao.upsert_buy_signature(token_id,buy_signature,trade_id)
        self.logger.info(f"🧾 Trade SUBMITTED saved — trade_id={trade_id} token={output_mint}")
        return trade_id
    
    def on_buy_status(self, signature: str, payload: dict, status: str):
        output_mint = payload["output_mint"]
        trade_dao = self.ctx.get("trade_dao")
        sig_dao = self.ctx.get("signatures_dao")
        try:
            trade = trade_dao.get_trade_by_buy_signature(signature)
            if not trade:
                trade = trade_dao.get_latest_trade_by_token_and_statuses(
                    output_mint, ("SUBMITTED", "CONFIRMED", "FINALIZED")
                )
                if not trade:
                    self.logger.error(
                        f"❌ BUY status but no trade found. output_mint={output_mint} sig={signature}"
                    )
                    return
                sig_dao.upsert_buy_signature(trade["token_id"], signature,trade["id"])
            status = str(status).lower()
            if status == "confirmed":
                prev = str(trade.get("status", "")).upper()
                if prev not in ("CONFIRMED", "FINALIZED"):
                    trade_dao.update_trade_status_with_ts(trade["id"], "CONFIRMED")
                self.logger.info(f"🟡 BUY {signature} CONFIRMED — {output_mint} (trade_id={trade['id']})")
                return
            if status == "finalized":
                prev = str(trade.get("status", "")).upper()
                if prev != "FINALIZED":
                    trade_dao.update_trade_status_with_ts(trade["id"], "FINALIZED")
                    self.ctx.get("trade_counter").increment()
                else:
                    self.logger.debug(f"⏩ BUY already FINALIZED — {output_mint} (trade_id={trade['id']})")

                self.logger.info(f"🟢 BUY {signature} FINALIZED — {output_mint} (trade_id={trade['id']})")

                trade_row = trade_dao.get_trade_by_id(trade["id"])
                with self.tokens_lock:
                    self.active_trades[output_mint] = trade_row
                notifier = self.ctx.get("notification_manager")
                notifier.notify_text(
                    f"✅ **BUY FINALIZED** — `{output_mint}`\n🔗 Signature: `{signature}`",
                    self.live_channel,
                )
                return

            self.logger.warning(f"⚠️ BUY {signature} returned unexpected status={status}")

        except Exception as e:
            self.logger.error(f"❌ _on_buy_status error: {e}", exc_info=True)
    
    def on_buy_fail_or_timeout(self, signature: str, payload: dict, status: str):
        output_mint = payload.get("output_mint")
        trade_dao = self.ctx.get("trade_dao")
        sig_dao = self.ctx.get("signatures_dao")

        trade = trade_dao.get_trade_by_buy_signature(signature)
        if not trade and output_mint:
            trade = trade_dao.get_latest_trade_by_token_and_statuses(
                output_mint,
                ("SUBMITTED", "CONFIRMED"),
            )

        if not trade:
            return

        try:
            sig_dao.upsert_buy_signature(trade["token_id"],signature,trade["id"])
        except Exception:
            pass

        try:
            exists = self.ctx.get("wallet_client").check_if_token_exists_in_wallet(output_mint)
        except Exception:
            exists = False

        if exists:
            trade_dao.update_trade_status_with_ts(trade["id"], "FINALIZED")
            self.logger.warning(f"🩹 BUY {status} but wallet HAS token -> treating as FINALIZED: {output_mint}")
            return

        if status == "failed":
            trade_dao.update_trade_status(trade["id"], "BUY_FAILED")
        else:
            trade_dao.update_trade_status(trade["id"], "BUY_TIMEOUT")

    def on_sell_fail_or_timeout(self, signature: str, payload: dict, status: str):
        token_mint = payload.get("token_mint")
        reason = payload.get("trigger_reason")
        trade_dao = self.ctx.get("trade_dao")
        sig_dao = self.ctx.get("signatures_dao")
        try:
            trade = trade_dao.get_trade_by_token(token_mint)
            if not trade:
                self.logger.warning(f"SELL {status} but no open trade found for {token_mint}")
                return
            try:
                sig_dao.upsert_sell_signature(trade["token_id"], signature,trade["id"])
            except Exception:
                pass
            if status == "failed":
                trade_dao.update_trade_status(trade["id"], "FINALIZED") 
                self.logger.error(f"❌ SELL failed for {token_mint} (sig={signature}) — reverted status back to FINALIZED. reason={reason}")
                with self.tokens_lock:
                    if token_mint in self.active_trades:
                        self.active_trades[token_mint]["status"] = "FINALIZED"
                return
            if status == "timeout":
                try:
                    trade_dao.update_trade_status(trade["id"], "SELL_TIMEOUT")
                    with self.tokens_lock:
                        if token_mint in self.active_trades:
                            self.active_trades[token_mint]["status"] = "SELL_TIMEOUT"
                except Exception:
                    self.logger.warning(f"⏱SELL timeout for {token_mint} (sig={signature}) — leaving status as-is (likely SELLING)")
                return
        except Exception as e:
            self.logger.error(f"❌ _on_sell_fail_or_timeout error: {e}", exc_info=True)

    def on_sell_status(self, signature: str, payload: dict, status: str):
        token_mint = payload.get("token_mint")
        reason = payload.get("trigger_reason")
        trade_dao = self.ctx.get("trade_dao")
        sig_dao = self.ctx.get("signatures_dao")
        jup = self.ctx.get("jupiter_client")

        try:
            trade = trade_dao.get_trade_by_token(token_mint)
            if not trade:
                self.logger.warning(f"⚠️ No open trade for {token_mint}")
                return

            entry_usd = float(trade.get("entry_usd", 0))
            current_price_usd = jup.get_token_price(token_mint)            
            if current_price_usd is None or current_price_usd <= 0:
                self.logger.warning(f"⚠️ Missing exit price for {token_mint}. Not closing trade yet.")
                try:
                    sig_dao.upsert_sell_signature(trade["token_id"], signature,trade["id"])
                except Exception:
                    pass
                return 
            pnl_percent = ((current_price_usd - entry_usd) / entry_usd) * 100 if entry_usd else 0 
            trade_dao.close_trade(
                trade_id=trade["id"],
                exit_usd=current_price_usd,
                pnl_percent=pnl_percent,
                trigger_reason=reason
            )

            token_id = trade["token_id"]
            sig_dao.upsert_sell_signature(token_id, signature,trade["id"])

            self.logger.info(
                f"💰 Trade closed for {token_mint} ({reason}) — PnL: {pnl_percent:.8f}% | Exit USD: {current_price_usd:.8f}"
            )
            notifier = self.ctx.get("notification_manager")
            notifier.notify_text(f"💰 **SELL EXECUTED** — `{token_mint}`\n📈 PnL: {pnl_percent:.8f}%\n💵 Exit USD: {current_price_usd:.8f}\n⚙️ Reason: {reason}",self.live_channel)
            self.tracker_logger.info({
                    "event": "sell",
                    "token_mint": token_mint,
                    "trigger": reason,
                    "pnl": pnl_percent,
                    "exit_usd": current_price_usd,
                    "signature": signature,
                    "simulated": False,
            })
            with self.tokens_lock:
                if token_mint in self.active_trades:
                    self.active_trades.pop(token_mint, None)
                    self.logger.debug(f"🧹 Removed {token_mint} from tracker cache.")
        except Exception as e:
            self.logger.error(f"❌ _on_sell_status error: {e}", exc_info=True)

    def request_exit(self, token_mint: str, trigger_reason: str) -> bool:
        trade_dao = self.ctx.get("trade_dao")

        trade = trade_dao.get_trade_by_token(token_mint)
        if not trade:
            self.logger.warning(f"⚠️ No open trade found to request exit for {token_mint}")
            return False

        status = str(trade.get("status", "")).upper()
        if status in ("EXIT_REQUESTED", "SELLING", "CLOSED"):
            self.logger.info(f"ℹ️ Exit already in progress or closed for {token_mint} ({status})")
            return False

        trade_dao.update_trade_status(trade["id"], "EXIT_REQUESTED")
        trade_dao.update_exit_data(trade["id"], trigger_reason)

        with self.tokens_lock:
            active = self.active_trades.get(token_mint)
            if active is not None:
                active = dict(active)
                active["status"] = "EXIT_REQUESTED"
                if trigger_reason is not None:
                    active["trigger_reason"] = trigger_reason
                self.active_trades[token_mint] = active
                self.logger.info(f"⚡ EXIT REQUESTED — {token_mint} trigger={trigger_reason}")
                return True
    
    def mark_sell_submitted(self, token_mint: str, signature: str, trigger_reason: str | None = None):
        trade_dao = self.ctx.get("trade_dao")
        sig_dao = self.ctx.get("signatures_dao")

        trade = trade_dao.get_trade_by_token(token_mint)
        if not trade:
            self.logger.warning(f"⚠️ No open trade found to mark SELLING for {token_mint}")
            return None

        trade_dao.update_trade_status(trade["id"], "SELLING")
        if trigger_reason:
            trade_dao.update_exit_data(trade["id"], trigger_reason)

        try:
            sig_dao.upsert_sell_signature(trade["token_id"], signature,trade["id"])
        except Exception:
            pass
        
        if not signature:
            self.logger.warning(f"⚠️ Sell TX failed for {token_mint}")
            return None   
        
        with self.tokens_lock:
            active = self.active_trades.get(token_mint)
            if active is not None:
                active = dict(active)
                active["status"] = "SELLING"
                if trigger_reason is not None:
                    active["trigger_reason"] = trigger_reason
                self.active_trades[token_mint] = active

        self.logger.info(f"📤 SELL SUBMITTED — {token_mint} (trade_id={trade['id']}, sig={signature})")
        return trade["id"]