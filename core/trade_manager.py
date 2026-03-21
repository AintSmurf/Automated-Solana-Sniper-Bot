from services.bot_context import BotContext
from helpers.framework_utils import run_bg, decimal_to_lamports
from concurrent.futures import Future



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
                return self.ctx.get("trade_lifecycle_service").insert_simulated_trade(output_mint, entry_price_usd, entry_price_usd)
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
            self.ctx.get("trade_lifecycle_service").insert_submitted_buy(data,buy_signature,output_mint)

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
            self.ctx.get("trade_lifecycle_service").mark_sell_submitted(token_mint=input_mint,signature=sell_signature,trigger_reason=trigger_reason)
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
                    output_mint = payload["output_mint"]

                    if status in ("confirmed", "finalized"):
                        self.ctx.get("trade_lifecycle_service").on_buy_status(signature, payload, status)
                        if status == "finalized":
                            self.pending_futures.pop(output_mint, None)
                        return

                    if status in ("failed", "timeout"):
                        self.ctx.get("trade_lifecycle_service").on_buy_fail_or_timeout(signature, payload, status)
                        self.pending_futures.pop(output_mint, None)
                        return

                    self.logger.warning(f"⚠️ BUY {signature} returned status={status}")
                    return

                if action == "sell":
                    token_mint = payload["token_mint"]
                    if status == "finalized":
                        self.ctx.get("trade_lifecycle_service").on_sell_status(signature, payload, status)
                        self.pending_futures.pop(token_mint, None)
                        return
                    if status == "confirmed":
                        exists = self.ctx.get("wallet_client").check_if_token_exists_in_wallet(token_mint)
                        if not exists:
                            self.ctx.get("trade_lifecycle_service").on_sell_status(signature, payload, status)
                            self.pending_futures.pop(token_mint, None)
                            return
                        self.logger.warning(
                            f"⚠️ SELL {signature} confirmed but token still in wallet: {token_mint} (not closing yet)"
                        )
                        return
                    if status == "failed":
                        self.ctx.get("trade_lifecycle_service").on_sell_fail_or_timeout(signature, payload, status)
                        self.pending_futures.pop(token_mint, None)
                        return
                    if status == "timeout":
                        self.ctx.get("trade_lifecycle_service").on_sell_fail_or_timeout(signature, payload, status)
                        self.pending_futures.pop(token_mint, None)
                        return
                    self.logger.warning(f"⚠️ SELL {signature} returned status={status} (not closing yet)")
                    return

            except Exception as e:
                self.logger.error(f"❌ Callback error ({action}): {e}", exc_info=True)

        return callback

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

