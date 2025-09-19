from services.bot_context import BotContext
from helpers.framework_utils import run_bg,decimal_to_lamports,parse_timestamp
import time
import os
import pandas as pd


class TraderManager:
    
    def __init__(self,ctx:BotContext):
        self.ctx = ctx
        self.tracker_logger =  ctx.get("tracker_logger")
        self.logger = ctx.get("logger")
    
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
            self.logger.info(f"✅ Buy SUCCESSFUL for {output_mint}")
            data = self.ctx.get("excel_utility").build_pending_buy_data(base_data,real_entry_price, token_received, usd_amount, buy_signature)
            self.ctx.get("excel_utility").save_pending_buy(data)
            future = run_bg(self.ctx.get("helius_client").verify_signature, buy_signature)
            future.add_done_callback(self._signature_finalize_callback(buy_signature, "buy"))
            run_bg(self._update_entry_price_with_balance,data,output_mint,usd_amount,name="finalize_entry_price")
            return buy_signature
        except Exception as e:
            self.logger.error(f"❌ Exception during buy: {e}")
            return None
    
    def sell(self, input_mint: str, output_mint: str) -> str:
        self.logger.info(f"🔄 Initiating sell order: Selling {input_mint} for {output_mint}")
        try:
            tokens = 0
            balances = self.ctx.get("wallet_client").get_account_balances()
            for token in balances:
                if token == input_mint:
                    lamport_amount = token['balance']
                    tokens = decimal_to_lamports(lamport_amount,self.ctx.get("helius_client").get_token_decimals(input_mint))
            if tokens == 0:
                self.logger.error(f"failed to sell token{input_mint}")
                return
            data = self.ctx.get("jupiter_client").get_quote_dict(input_mint, output_mint,tokens)
            quote = data["quote"]
            token_received = data["outAmount"] 
            txn_64 = self.ctx.get("jupiter_client").get_swap_transaction(quote)
            sell_signature =self.ctx.get("helius_client").send_transaction(txn_64)  
            self.logger.info(f" Sell submited: Signature: {sell_signature}")
            sol_price = self.ctx.get("jupiter_client").get_sol_price()
            exit_usd = token_received * sol_price
            base_data =  self.ctx.get("excel_utility").load_closed_positions(self.ctx.settings["SIM"])      
            future = run_bg(self.ctx.get("helius_client").verify_signature, sell_signature)
            future.add_done_callback(self._signature_finalize_callback(sell_signature, "sell"))
            run_bg(self._update_exit_with_balance,base_data,output_mint,exit_usd,name="finalize_exit_price")
            return sell_signature

        except Exception as e:
            self.logger.error(f"❌ Exception during sell: {e}")
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

    def _update_exit_with_balance(self, data: dict, token_mint: str, exit_usd: float):
        try:
            data = self.ctx.get("excel_utility").update_sell(data,exit_usd)
            self.ctx.get("excel_utility").save_closed_position(data)
            self.logger.info(f"📊 Exit finalized for {token_mint}: ${exit_usd:.4f} USD")
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
                self.ctx.get("excel_utility").save_closed_poistions(data, True)
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
