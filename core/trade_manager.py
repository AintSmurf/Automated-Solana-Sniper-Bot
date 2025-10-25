from services.bot_context import BotContext
from helpers.framework_utils import run_bg,decimal_to_lamports,parse_timestamp
import time
import os
import pandas as pd
from concurrent.futures import Future


class TraderManager:
    
    def __init__(self,ctx:BotContext):
        self.ctx = ctx
        self.tracker_logger =  ctx.get("tracker_logger")
        self.logger = ctx.get("logger")
        self.pending_futures: dict[str, Future] = {}

    def buy(self, input_mint: str, output_mint: str, usd_amount: int, sim: bool) -> str:
        self.logger.info(f"🔄 Initiating buy for ${usd_amount} — Token: {output_mint}")
        try:
            token_amount = self.ctx.get("jupiter_client").get_solana_token_worth_in_dollars(usd_amount)
            data = self.ctx.get("jupiter_client").get_quote_dict(input_mint, output_mint, token_amount)
            quote_price = data["quote_price"]
            token_received = data["outAmount"]
            quote = data["quote"]     
            base_data = self.ctx.get("excel_utility").build_base_data(input_mint, output_mint, quote_price)
            real_entry_price = usd_amount / token_received
            if sim: 
                data = self.ctx.get("excel_utility").build_simulated_buy_data(base_data, real_entry_price, token_received)
                self.ctx.get("excel_utility").save_simulated_buy(data)
                return "SIMULATED"
            txn_64 = self.ctx.get("jupiter_client").get_swap_transaction(quote)
            buy_signature =self.ctx.get("helius_client").send_transaction(txn_64)
            if not buy_signature:
                self._record_failed_token(output_mint, "Transaction send failed")
                return None
            self.logger.info(f"✅ Buy SUCCESSFUL for {output_mint}")
            data = self.ctx.get("excel_utility").build_pending_buy_data(base_data,output_mint,real_entry_price, token_received, usd_amount, buy_signature)
            self.ctx.get("excel_utility").save_pending_buy(data)
            future = run_bg(self.ctx.get("helius_client").verify_signature, buy_signature)
            self.pending_futures[output_mint] = future
            future.add_done_callback(self._signature_finalize_callback(buy_signature, "buy"))
            run_bg(self._update_entry_price_with_balance,data,output_mint,usd_amount,name="finalize_entry_price")
            return buy_signature
        except Exception as e:
            self.logger.error(f"❌ Exception during buy: {e}")
            self._record_failed_token(input_mint, str(e))
            return None
    
    def sell(self, input_mint: str, output_mint: str, slippage_override: float = None) -> str:
        self.logger.info(f"🔄 Initiating sell order: Selling {input_mint} for {output_mint}")
        try:
            fut = self.pending_futures.get(input_mint)
            if fut and not fut.done():
                self.logger.info(f"🕒 Waiting for pending buy of {input_mint} to finalize before selling...")
                try:
                    status = fut.result(timeout=3)
                    self.logger.info(f"✅ Buy finalized ({status}) — continuing with sell.")
                except Exception as e:
                    self.logger.warning(f"⚡ Timeout or error waiting on {input_mint}: {e}; continuing sell anyway.")
                finally:
                    self.pending_futures.pop(input_mint, None)
        except Exception as e:
            self.logger.error(f"⚡ Timeout or error waiting on {input_mint}: {e}")
        try:
            tokens = 0
            balances = self.ctx.get("wallet_client").get_account_balances()
            for token in balances:
                if token["token_mint"] == input_mint:
                    lamport_amount = token['balance']
                    tokens = decimal_to_lamports(lamport_amount,self.ctx.get("helius_client").get_token_decimals(input_mint))
            if tokens == 0:
                self.logger.error(f"❌ Failed to sell {input_mint}: No balance found.")
                self._record_failed_token(input_mint, "No balance found in wallet", stage="balance")
                return
            data = self.ctx.get("jupiter_client").get_quote_dict(input_mint, output_mint, tokens, slippage_override=slippage_override)
            if not data or "quote" not in data or "outAmount" not in data:
                self._record_failed_token(input_mint, "Jupiter quote failed (RPC or empty data)", stage="quote")
                return None
            quote = data["quote"]
            token_received = data["outAmount"] 
            txn_64 = self.ctx.get("jupiter_client").get_swap_transaction(quote)
            if not txn_64:
                self._record_failed_token(input_mint, "Swap transaction build failed (RPC error)", stage="swap_build")
                return None
            sell_signature =self.ctx.get("helius_client").send_transaction(txn_64)
            if not sell_signature:
                self._record_failed_token(input_mint, "Transaction send failed (likely slippage or RPC drop)", stage="send_tx")
                return None
            self.logger.info(f" Sell submited: Signature: {sell_signature}")
            sol_price = self.ctx.get("jupiter_client").get_sol_price()
            exit_usd = token_received * sol_price
            base_data =  self.ctx.get("excel_utility").load_closed_positions(self.ctx.settings["SIM_MODE"])      
            future = run_bg(self.ctx.get("helius_client").verify_signature, sell_signature)
            future.add_done_callback(self._signature_finalize_callback(sell_signature, "sell"))
            run_bg(self._update_exit_with_balance, base_data, input_mint, exit_usd, sell_signature, name="finalize_exit_price")
            return sell_signature

        except Exception as e:
            self.logger.error(f"❌ Exception during sell: {e}")
            self._record_failed_token(input_mint, str(e), stage="exception")
            return None
    
    def _update_entry_price_with_balance(self,data:dict,output_mint: str, usd_amount: float):
        MAX_RETRIES = 15
        WAIT_TIME = 2
        token_received = 0

        for attempt in range(MAX_RETRIES):
            time.sleep(WAIT_TIME)
            balances = self.ctx.get("wallet_client").get_account_balances()
            token_info = next((b for b in balances if b['token_mint'] == output_mint), None)
            if token_info and token_info['balance'] > 0:
                token_received = token_info['balance']
                self.logger.info(f"✅ Token received after buy: {token_received}")
                break
            self.logger.warning(f"🔁 Attempt {attempt + 1}: Token not received yet...")

        if token_received == 0:
            return

        real_entry_price = usd_amount / token_received

        data = self.ctx.get("excel_utility").update_buy(data,"BOUGHT",real_entry_price)
        self.ctx.get("excel_utility").save_pending_buy(data)       
        self.logger.info(f"📊 Entry price finalized for {output_mint}: {real_entry_price:.8f} USD")

    def _update_exit_with_balance(self, data: dict, token_mint: str, exit_usd: float,sell_signature: str):
        try:
            data = self.ctx.get("excel_utility").update_sell(data,exit_usd,sell_signature)
            self.ctx.get("excel_utility").save_closed_poistions(data,self.ctx.settings["SIM_MODE"])
            self.logger.info(f"📊 Exit finalized for {token_mint}: ${exit_usd:.4f} USD")
            self.tracker_logger.info({
            "event": "sell",
            "token_mint": token_mint,
        })
        except Exception as e:
            self.logger.error(f"❌ Failed to update exit for {token_mint}: {e}")
    
    def _signature_finalize_callback(self, signature: str, action: str):
        def callback(fut):
            try:
                status = fut.result()
                if status == "finalized":
                    self.logger.info(f"📊 {action.upper()} finalized on-chain: {signature}")
                else:
                    self.logger.warning(f"⚠️ {action.upper()} {signature} not finalized (status={status})")
            except Exception as e:
                self.logger.error(f"❌ Error finalizing {action.upper()} {signature}: {e}", exc_info=True)
        return callback

    def manual_close(self, token_mint: str, trigger="MANUAL_UI"):
        try:
            file_path = os.path.join(
                self.ctx.get("excel_utility").OPEN_POISTIONS,
                "simulated_tokens.csv" if self.ctx.settings["SIM_MODE"] else "open_positions.csv"
            )

            if not os.path.exists(file_path):
                self.logger.warning(f"⚠️ No open positions file found at {file_path}")
                return False

            df = pd.read_csv(file_path)
            row = df[df["Token_bought"] == token_mint]
            if row.empty:
                self.logger.warning(f"⚠️ No open position found for {token_mint}")
                return False

            row = row.iloc[0]
            input_mint = row["Token_sold"]
            buy_signature = row["Buy_Signature"]
            buy_price_usd = float(row["Entry_USD"])
            buy_time = parse_timestamp(row["Buy_Timestamp"])
            current_price_usd = self.ctx.get("jupiter_client").get_token_price(token_mint)
            pnl = ((current_price_usd - buy_price_usd) / buy_price_usd) * 100

            if self.ctx.settings["SIM_MODE"]:
                data = self.ctx.get("excel_utility").build_closed_data(
                    token_mint, buy_signature, buy_price_usd, buy_time, pnl, current_price_usd, trigger
                )
                self.ctx.get("excel_utility").save_closed_poistions(data, self.ctx.settings["SIM_MODE"])
                df = df[df["Token_bought"] != token_mint]
                df.to_csv(file_path, index=False)
                self.logger.info(f"🛑 SIMULATED manual close logged for {token_mint} (trigger={trigger})")
            else:
                self.sell(token_mint, input_mint)
                self.logger.info(f"🛑 Manual SELL submitted for {token_mint} (trigger={trigger})")

            return True

        except Exception as e:
            self.logger.error(f"❌ Manual close failed for {token_mint}: {e}", exc_info=True)
            return False

    def _record_failed_token(self, token_name: str, reason: str, stage: str = "unknown"):
        try:
            data = self.ctx.get("excel_utility").build_failed_transactions(token_name, reason, retries=0)
            data["stage"] = stage
            self.ctx.get("excel_utility").save_failed_buy(data)
            self.logger.warning(f"⚠️ Logged failed token {token_name}: {reason} (stage={stage})")
        except Exception as e:
            self.logger.error(f"❌ Failed to record failed token {token_name}: {e}", exc_info=True)

    def retry_failed_tokens(self):
        file = os.path.join(self.ctx.get("excel_utility").FAILED_TOKENS, "failed_tokens.csv")
        if not os.path.exists(file):
            return

        try:
            df = pd.read_csv(file)
        except Exception:
            return
        if df.empty:
            return

        if "retries" not in df.columns:
            df["retries"] = 0

        retried = []
        base_slippage = float(self.ctx.settings.get("SLPG", 3.0))

        for _, row in df.iterrows():
            token = row.get("token_name")
            retries = int(row.get("retries", 0))

            if not token:
                continue
            if retries >= 3:
                continue

            new_slippage = base_slippage + (0.5 * (retries + 1))
            self.logger.info(f"🔁 Retrying SELL for {token} (attempt {retries+1}/3) with slippage={new_slippage:.1f}%")

            try:
                sig = self.sell(
                    token,
                    "So11111111111111111111111111111111111111112",
                    slippage_override=new_slippage,
                )
                if sig:
                    self.logger.info(f"✅ Retry success for {token} ({sig})")
                    self.tracker_logger.info({"event": "sell", "token_mint": token})
                    retried.append(token)
                else:
                    df.loc[df["token_name"] == token, "retries"] = retries + 1
                    self.logger.warning(f"⚠️ Retry failed for {token}")
            except Exception as e:
                df.loc[df["token_name"] == token, "retries"] = retries + 1
                self.logger.error(f"❌ Retry exception for {token}: {e}")

        if retried:
            df = df[~df["token_name"].isin(retried)]
        df.to_csv(file, index=False)

    def _retry_loop(self,retry_stop):
        while not retry_stop.is_set():
            try:
                self.retry_failed_tokens()
            except Exception as e:
                self.logger.error(f"Retry loop error: {e}")
            time.sleep(30)
