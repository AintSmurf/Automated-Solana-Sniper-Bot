from services.bot_context import BotContext
from helpers.framework_utils import run_bg, decimal_to_lamports
from datetime import datetime, timezone
from concurrent.futures import Future
from helpers.framework_utils import get_formatted_date_str
import time


class TraderManager:
    def __init__(self, ctx: BotContext):
        self.ctx = ctx
        self.logger = ctx.get("logger")
        self.tracker_logger = ctx.get("tracker_logger")
        self.pending_futures: dict[str, Future] = {}
        self.live_channel = ctx.settings_manager.get_notification_settings()["DISCORD"]["LIVE_CHANNEL"]

    def buy(self, input_mint: str, output_mint: str, usd_amount: int, sim: bool) -> str:
        self.logger.info(f"🔄 Initiating BUY for ${usd_amount} — Token: {output_mint}")
        try:
            token_amount = self.ctx.get("jupiter_client").get_solana_token_worth_in_dollars(usd_amount)
            data = self.ctx.get("jupiter_client").get_quote_dict(input_mint, output_mint, token_amount)
            if not data or "quote" not in data or "outAmount" not in data:
                self.logger.warning(f"⚠️ Jupiter quote failed for BUY {output_mint}")
                return None
            token_received = data["outAmount"]
            if token_received <= 0:
                self.logger.warning(f"⚠️ Bad outAmount for BUY {output_mint}: {token_received}")
                return None
            quote = data["quote"]
            entry_price_usd = float(data.get("entry_usd") or 0.0)

            if sim:
                return self._insert_simulated_trade(output_mint, entry_price_usd, entry_price_usd)
            use_sender = self.ctx.settings["USE_SENDER"]["BUY"]
            if use_sender:
                txn_64 = self.ctx.get("jupiter_client").get_swap_transaction_for_sender(quote)
                buy_signature = self.ctx.get("helius_client").send_via_sender(txn_64)
            else:
                txn_64 = self.ctx.get("jupiter_client").get_swap_transaction(quote)
                buy_signature = self.ctx.get("helius_client").send_transaction(txn_64)
            if not buy_signature:
                self.logger.error(f"❌ Transaction send failed for {output_mint}")
                return None

            self.logger.info(f"✅ Transaction submitted — signature: {buy_signature}")
            self.insert_submitted_buy(data,buy_signature,output_mint)

            payload = {"output_mint": output_mint,"entry_price_usd": entry_price_usd,"usd_spent": usd_amount}        
            fut = run_bg(self.ctx.get("helius_client").verify_signature, buy_signature)
            fut.add_done_callback(lambda f: self._signature_status_callback(buy_signature, "buy", payload)(f))
            self.pending_futures[output_mint] = fut
            return buy_signature

        except Exception as e:
            self.logger.error(f"❌ BUY Exception: {e}", exc_info=True)
            return None

    def sell(self, input_mint: str, output_mint: str, trigger_reason: str = None, slippage_override: float = None) -> str:
        self.logger.info(f"🔄 Initiating SELL — {input_mint} → {output_mint}")
        try:
            trade_dao = self.ctx.get("trade_dao")
            trade = trade_dao.get_trade_by_token(input_mint)
            if trade:
                trade_dao.update_trade_status(trade["id"], "SELLING")
                self.logger.debug(f"📦 Marked trade {trade['id']} ({input_mint}) as SELLING")
        except Exception as e:
            self.logger.error(f"❌ Failed to update trade status to SELLING for {input_mint}: {e}", exc_info=True)
        try:
            fut = self.pending_futures.get(input_mint)
            if fut and not fut.done():
                try:
                    fut.result(timeout=3)
                except Exception:
                    self.logger.warning(f"⚠️ Waiting timeout for {input_mint} confirmation.")

            tokens = 0
            balances = self.ctx.get("wallet_client").get_token_balances()
            for token in balances:
                if token["token_mint"] == input_mint:
                    lamport_amount = token["balance"]
                    tokens = decimal_to_lamports(
                        lamport_amount,
                        self.ctx.get("helius_client").get_token_decimals(input_mint)
                    )

            if tokens == 0:
                self.logger.warning(f"⚠️ No balance for {input_mint}, skipping SELL.")
                return None

            data = self.ctx.get("jupiter_client").get_quote_dict(input_mint, output_mint, tokens, slippage_override)
            if not data or "quote" not in data or "outAmount" not in data:
                self.logger.warning(f"⚠️ Jupiter quote failed for {input_mint}")
                return None

            use_sender = self.ctx.settings.get("USE_SENDER", {}).get("SELL", False)
            if use_sender:
                txn_64 = self.ctx.get("jupiter_client").get_swap_transaction_for_sender(data["quote"])
                sell_signature = self.ctx.get("helius_client").send_via_sender(txn_64)
            else:
                txn_64 = self.ctx.get("jupiter_client").get_swap_transaction(data["quote"])
                sell_signature = self.ctx.get("helius_client").send_transaction(txn_64)
            if not sell_signature:
                self.logger.warning(f"⚠️ Sell TX failed for {input_mint}")
                return None

            self.logger.info(f"📤 Sell submitted — signature: {sell_signature}")

            payload = {"token_mint": input_mint, "trigger_reason": trigger_reason}
            fut = run_bg(self.ctx.get("helius_client").verify_signature, sell_signature)
            fut.add_done_callback(lambda f: self._signature_status_callback(sell_signature, "sell", payload)(f))
            self.pending_futures[input_mint] = fut
            return sell_signature

        except Exception as e:
            self.logger.error(f"❌ SELL Exception: {e}", exc_info=True)
            return None

    def _signature_status_callback(self, signature: str, action: str, payload: dict | None = None):
        def callback(fut):
            try:
                status = str(fut.result() or "").lower()
                if action == "buy":
                    if status in ("confirmed", "finalized"):
                        self._on_buy_status(signature, payload, status)
                    elif status in ("failed", "timeout"):
                        self._on_buy_fail_or_timeout(signature, payload, status)
                    else:
                        self.logger.warning(f"⚠️ BUY {signature} returned status={status}")
                    return
                if action == "sell":
                    token_mint = payload["token_mint"]

                    if status == "finalized":
                        self._on_sell_status(signature, payload, status)
                        return
                    if status == "confirmed":
                        exists = self.ctx.get("wallet_client").check_if_token_exists_in_wallet(token_mint)
                        if not exists:
                            self._on_sell_status(signature, payload, status)
                            return
                        self.logger.warning(
                            f"⚠️ SELL {signature} confirmed but token still in wallet: {token_mint} (not closing yet)"
                        )
                        return
                    if status == "failed":
                        self._on_sell_fail_or_timeout(signature, payload, status)
                        return

                    if status == "timeout":
                        self._on_sell_fail_or_timeout(signature, payload, status)
                        return
                    self.logger.warning(f"⚠️ SELL {signature} returned status={status} (not closing yet)")
                    return
            except Exception as e:
                self.logger.error(f"❌ Callback error ({action}): {e}", exc_info=True)
        return callback

    def _on_buy_status(self, signature: str, payload: dict, status: str):
        output_mint = payload["output_mint"]
        trade_dao = self.ctx.get("trade_dao")
        sig_dao = self.ctx.get("signatures_dao")
        tracker = self.ctx.get("open_position_tracker")
        config_id = self.ctx.get("config_id") 


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
                sig_dao.upsert_buy_signature(trade["token_id"], signature)
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
                if tracker:
                    with tracker.tokens_lock:
                        tracker.active_trades[output_mint] = trade_row
                self.pending_futures.pop(output_mint, None)
                notifier = self.ctx.get("notification_manager")
                notifier.notify_text(
                    f"✅ **BUY FINALIZED** — `{output_mint}`\n🔗 Signature: `{signature}`",
                    self.live_channel,
                )
                return

            self.logger.warning(f"⚠️ BUY {signature} returned unexpected status={status}")

        except Exception as e:
            self.logger.error(f"❌ _on_buy_status error: {e}", exc_info=True)

    def _on_sell_status(self, signature: str, payload: dict, status: str):
        token_mint = payload.get("token_mint")
        reason = payload.get("trigger_reason")

        trade_dao = self.ctx.get("trade_dao")
        sig_dao = self.ctx.get("signatures_dao")
        tracker = self.ctx.get("open_position_tracker")
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
                    sig_dao.upsert_sell_signature(trade["token_id"], signature)
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
            sig_dao.upsert_sell_signature(token_id, signature)

            self.logger.info(
                f"💰 Trade closed for {token_mint} ({reason}) — PnL: {pnl_percent:.8f}% | Exit USD: {current_price_usd:.8f}"
            )
            self.pending_futures.pop(token_mint, None)     
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
            if tracker and token_mint in tracker.active_trades:
                tracker.active_trades.pop(token_mint, None)
                self.logger.debug(f"🧹 Removed {token_mint} from tracker cache.")

        except Exception as e:
            self.logger.error(f"❌ _on_sell_status error: {e}", exc_info=True)

    def _insert_simulated_trade(self, output_mint: str, real_entry_price: float, entry_price: float):
        """Insert a simulated trade with UTC timestamps for consistency."""
        token_dao = self.ctx.get("token_dao")
        trade_dao = self.ctx.get("trade_dao")
        sig_dao = self.ctx.get("signatures_dao")
        tracker = self.ctx.get("open_position_tracker")
        config_id = self.ctx.get("config_id")

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
            config_id=config_id
        )
        sig_dao.upsert_buy_signature(token_id, f"SIMULATED_BUY_{get_formatted_date_str()}")

        trade_row = trade_dao.get_trade_by_id(trade_id)
        tracker.active_trades[output_mint] = trade_row
        self.ctx.get("trade_counter").increment()

        self.logger.debug(f"📡 Added {output_mint} (SIM) to tracker instantly.")
        self.logger.info(f"🧪 Simulated trade created for {output_mint} (trade_id={trade_id})")

        return "SIMULATED"

    def _has_token_balance(self, token_mint: str, min_balance: float = 0.000001) -> bool:
        try:
            balances = self.ctx.get("wallet_client").get_account_balances()
            for b in balances:
                if b.get("token_mint") == token_mint and float(b.get("balance", 0)) > min_balance:
                    self.logger.debug(f"✅ Balance check passed for {token_mint}: {b['balance']}")
                    return True
            self.logger.warning(f"⚠️ {token_mint} not found in wallet or balance too low.")
            return False
        except Exception as e:
            self.logger.error(f"❌ Balance check failed for {token_mint}: {e}", exc_info=True)
            return False

    def has_pending_trades(self) -> bool:
        return any(not f.done() for f in self.pending_futures.values())

    def insert_submitted_buy(self, data: dict, buy_signature: str, output_mint: str):
        token_dao = self.ctx.get("token_dao")
        trade_dao = self.ctx.get("trade_dao")
        sig_dao = self.ctx.get("signatures_dao")
        config_id = self.ctx.get("config_id")
        existing = trade_dao.get_latest_trade_by_token_and_statuses(
            output_mint,  ("SUBMITTED", "CONFIRMED", "FINALIZED")
        )
        if existing:
            self.logger.debug(
                f"⏩ Existing open-ish trade for {output_mint} (trade_id={existing['id']}, status={existing.get('status')})"
            )
            sig_dao.upsert_buy_signature(existing["token_id"], buy_signature)
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
        )
        sig_dao.upsert_buy_signature(token_id, buy_signature)

        self.logger.info(f"🧾 Trade SUBMITTED saved — trade_id={trade_id} token={output_mint}")
        return trade_id
    
    def _on_sell_fail_or_timeout(self, signature: str, payload: dict, status: str):
        token_mint = payload.get("token_mint")
        reason = payload.get("trigger_reason")
        trade_dao = self.ctx.get("trade_dao")
        sig_dao = self.ctx.get("signatures_dao")
        tracker = self.ctx.get("open_position_tracker")
        try:
            trade = trade_dao.get_trade_by_token(token_mint)
            if not trade:
                self.logger.warning(f"SELL {status} but no open trade found for {token_mint}")
                return
            try:
                sig_dao.upsert_sell_signature(trade["token_id"], signature)
            except Exception:
                pass
            if status == "failed":
                trade_dao.update_trade_status(trade["id"], "FINALIZED") 
                self.logger.error(f"❌ SELL failed for {token_mint} (sig={signature}) — reverted status back to FINALIZED. reason={reason}")
                if tracker and token_mint in tracker.active_trades:
                    tracker.active_trades[token_mint]["status"] = "FINALIZED"
                    return
            if status == "timeout":
                try:
                    trade_dao.update_trade_status(trade["id"], "SELL_TIMEOUT")
                    self.logger.warning(f"⏱SELL timeout for {token_mint} (sig={signature}) — marked SELL_TIMEOUT")
                except Exception:
                    self.logger.warning(f"⏱SELL timeout for {token_mint} (sig={signature}) — leaving status as-is (likely SELLING)")
                return
        except Exception as e:
            self.logger.error(f"❌ _on_sell_fail_or_timeout error: {e}", exc_info=True)
    
    def _on_buy_fail_or_timeout(self, signature: str, payload: dict, status: str):
        output_mint = payload.get("output_mint")
        trade_dao = self.ctx.get("trade_dao")

        trade = trade_dao.get_trade_by_buy_signature(signature)
        if not trade and output_mint:
            trade = trade_dao.get_latest_trade_by_token_and_statuses(output_mint, ("SUBMITTED", "CONFIRMED"))
        if not trade:
            return
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
        self.pending_futures.pop(output_mint, None)

