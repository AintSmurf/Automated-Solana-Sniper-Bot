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
            quote_price = data["quote_price"]
            token_received = data["outAmount"]
            quote = data["quote"]
            real_entry_price = usd_amount / token_received

            if sim:
                return self._insert_simulated_trade(output_mint, real_entry_price, real_entry_price)

            # Send transaction
            use_sender = self.ctx.settings.get("USE_SENDER", {}).get("BUY", False)
            
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

            payload = {"output_mint": output_mint, "usd_amount": real_entry_price}
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
            balances = self.ctx.get("wallet_client").get_account_balances()
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
            return sell_signature

        except Exception as e:
            self.logger.error(f"❌ SELL Exception: {e}", exc_info=True)
            return None

    def _signature_status_callback(self, signature: str, action: str, payload: dict | None = None):
        def callback(fut):
            try:
                status = fut.result()
                if status in ("confirmed", "finalized"):
                    self.logger.info(f"📊 {action.upper()} {signature} {status}")
                    if action == "buy":
                        self._on_buy_status(signature, payload, status)
                    elif action == "sell":
                        self._on_sell_status(signature, payload, status)
                else:
                    self.logger.warning(f"⚠️ {action.upper()} {signature} returned status={status}")
            except Exception as e:
                self.logger.error(f"❌ Callback error ({action}): {e}", exc_info=True)
        return callback

    def _on_buy_status(self, signature: str, payload: dict, status: str):
        output_mint = payload["output_mint"]
        usd_amount = float(payload["usd_amount"])
        sim = self.ctx.settings.get("SIM_MODE", False)
        now_utc = datetime.now(timezone.utc)

        token_dao = self.ctx.get("token_dao")
        trade_dao = self.ctx.get("trade_dao")
        sig_dao = self.ctx.get("signatures_dao")
        tracker = self.ctx.get("open_position_tracker")

        try:
            for attempt in range(3):
                if self._has_token_balance(output_mint):
                    break
                self.logger.debug(f"⏳ Waiting for wallet to reflect {output_mint} (attempt {attempt+1}/3)")
                time.sleep(3)
            else:
                self.logger.error(f"❌ Skipping trade insert — {output_mint} never appeared in wallet after TX {signature}")
                return
            if status == "confirmed":
                self.logger.info(f"🟢 {output_mint} confirmed + balance present — marking as FINALIZED")
                status = "finalized"

            token_id = token_dao.get_or_create_token(output_mint, signature)
            trade_id = trade_dao.insert_trade(
                token_id, "BUY", usd_amount, simulation=sim, status=status.upper(),
                confirmed_at=now_utc if status == "confirmed" else None,
                finalized_at=now_utc if status == "finalized" else None
            )
            sig_dao.insert_signature(token_id, buy_signature=signature)
            trade_row = trade_dao.get_trade_by_id(trade_id)
            tracker.active_trades[output_mint] = trade_row
            self.logger.info(f"✅ Trade {output_mint} {status.upper()} + Signature saved + Tracker updated")
            notifier = self.ctx.get("notification_manager")
            notifier.notify_text(f"✅ **BUY FINALIZED** — `{output_mint}`\n💵 USD: {usd_amount:.8f}\n🔗 Signature: `{signature}`",self.live_channel)
            self.ctx.get("trade_counter").increment()

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
            pnl_percent = ((current_price_usd - entry_usd) / entry_usd) * 100 if entry_usd else 0

            trade_dao.close_trade(
                trade_id=trade["id"],
                exit_usd=current_price_usd,
                pnl_percent=pnl_percent,
                trigger_reason=reason
            )

            token_id = trade["token_id"]
            sig_dao.update_sell_signature(token_id, signature)

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
        )
        sig_dao.insert_signature(token_id, buy_signature=f"SIMULATED_BUY_{get_formatted_date_str()}", sell_signature=None)

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
