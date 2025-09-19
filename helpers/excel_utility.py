import os
import pandas as pd
from helpers.logging_manager import LoggingHandler
from datetime import datetime

# set up logger
logger = LoggingHandler.get_logger()


class ExcelUtility:
    def __init__(self):
        #1st layer
        self.base_dir = os.path.abspath("results")

        #2nd layer      
        self.TOKENS_DIR = os.path.join(self.base_dir, "tokens")
        self.BACKTEST_DIR = os.path.join(self.base_dir, "backtest")
        self.NOTIFICATIONS = os.path.join(self.base_dir, "notifications")

        #3rd layer
        self.OPEN_POISTIONS = os.path.join(self.TOKENS_DIR, "open_poistions")
        self.CLOSED_POISTIONS = os.path.join(self.TOKENS_DIR, "closed_poistions")
        self.FAILED_TOKENS = os.path.join(self.TOKENS_DIR, "failed_tokens")


        self.create_folders()

    def create_folders(self)->None:
        os.makedirs(self.TOKENS_DIR, exist_ok=True)
        os.makedirs(self.BACKTEST_DIR, exist_ok=True)
        os.makedirs(self.OPEN_POISTIONS, exist_ok=True)
        os.makedirs(self.CLOSED_POISTIONS, exist_ok=True)
        os.makedirs(self.FAILED_TOKENS, exist_ok=True)
        os.makedirs(self.NOTIFICATIONS, exist_ok=True)
        logger.info("✅ Successfully created folders ..")

    def save_to_csv(self, directory, filename, data) -> None:
        filepath = os.path.join(directory, filename)

        # If single row dict → wrap in list
        if isinstance(data, dict):
            df = pd.DataFrame([data])
        else:
            df = pd.DataFrame(data)

        if os.path.exists(filepath):
            existing_df = pd.read_csv(filepath)
            updated_df = pd.concat([existing_df, df], ignore_index=True)

            # 🔑 drop duplicates globally
            updated_df = updated_df.drop_duplicates()
        else:
            updated_df = df

        updated_df.to_csv(filepath, index=False)
        logger.debug(f"✅ Data saved to {filepath} (dedup applied)")

    def remove_row_by_token(self, filepath: str, token_mint: str)->None:
        try:
            df = pd.read_csv(filepath)
            initial_len = len(df)
            df = df[df["Token_bought"] != token_mint]
            df.to_csv(filepath, index=False)

            if len(df) < initial_len:
                logger.debug(f"🧼 Removed token {token_mint} from {filepath}")
            else:
                logger.warning(f"⚠️ Token {token_mint} not found in {filepath}")
        except Exception as e:
            logger.error(f"❌ Failed to remove token from {filepath}: {e}")
    
    def load_closed_positions(self, sim:bool)->pd.DataFrame:
        filename = f"simulated_closed_positions.csv" if sim else f"closed_positions.csv"
        filepath = os.path.join(self.CLOSED_POISTIONS, filename)

        if not os.path.exists(filepath):
            logger.warning(f"⚠️ {filename} does not exist yet.")
            return pd.DataFrame() 
        try:
            return pd.read_csv(filepath)
        except Exception as e:
            logger.error(f"❌ Failed to load {filename}: {e}")
            return pd.DataFrame()

    def build_base_data(self, input_mint, output_mint, quote_price)->dict:
        now = datetime.now()
        timestamp_str = now.strftime("%Y-%m-%d %H:%M:%S")
        return {
            "Buy_Timestamp": timestamp_str,
            "Quote_Price": quote_price,
            "Token_sold": input_mint,
            "Token_bought": output_mint,
        }

    def build_simulated_buy_data(self, base_data, real_entry_price, token_received)->dict:
        base_data.update({
            "type": "SIMULATED_BUY",
            "Real_Entry_Price": real_entry_price,
            "Token_Received": token_received,
            "SentToDiscord": False,
            "Buy_Signature": "SIMULATED_BUY",
            "Entry_USD": real_entry_price,
        })
        return base_data

    def build_failed_buy_data(self, base_data, error_code, error_message)->dict:
        base_data.update({
            "type": "FAILED_BUY",
            "Error_Code": error_code,
            "Error_Message": error_message,
        })
        return base_data

    def build_pending_buy_data(self, base_data, real_entry_price, token_received, usd_amount,  buy_signature)->dict:
        base_data.update({
            "Real_Entry_Price": real_entry_price,
            "Entry_USD": usd_amount,
            "Token_Received": token_received,
            "type": "PENDING",
            "Sold_At_Price": 0,
            "SentToDiscord": False,
            "Buy_Signature": buy_signature,
        })
        return base_data
    
    def save_simulated_buy(self, data: dict)->None:
        self.save_to_csv(self.OPEN_POISTIONS, f"simulated_tokens.csv", data)
        self.save_discord(data)

    def save_failed_buy(self, data: dict)->None:
        date_str = self._get_date_str()
        self.save_to_csv(self.FAILED_TOKENS, f"failed_buys_{date_str}.csv", data)

    def save_pending_buy(self, data: dict)->None:
        self.save_to_csv(self.OPEN_POISTIONS, f"bought_tokens.csv", data)
        self.save_to_csv(self.OPEN_POISTIONS, f"open_positions.csv", data)
        self.save_discord(data)
    
    def update_signature_status(self, signature: str, price: float = None, status: str = None) -> None:
        file_path = os.path.join(self.OPEN_POISTIONS, f"open_positions.csv")

        if not os.path.exists(file_path):
            return

        try:
            df = pd.read_csv(file_path)

            if "Signature" not in df.columns:
                return

            mask = df["Signature"] == signature
            if not mask.any():
                return

            if status is not None:
                df.loc[mask, "type"] = "buy"
            if price is not None:
                df.loc[mask, "Real_Entry_Price"] = price

            df.to_csv(file_path, index=False)
            logger.info(f"✏️ Updated {signature} → status={status}, price={price}")

        except Exception as e:
            logger.error(f"❌ Failed to update {file_path} for {signature}: {e}", exc_info=True)

    def save_discord(self, data: dict)->None:
        date_str = self._get_date_str()
        self.save_to_csv(self.NOTIFICATIONS, f"discord_{date_str}.csv", data)
    
    def build_post_buy_data(self,token_mint:str,liquidity:float,market_cap:float,score:int,stats:dict,results:dict)->dict:
        return {
                "Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "Token Mint": token_mint,
                "Liquidity (Estimated)": liquidity,
                "Market Cap": market_cap,
                "Score": score,
                "LP_Check": results["LP_Check"],
                "Holders_Check": results["Holders_Check"],
                "Volume_Check": results["Volume_Check"],
                "MarketCap_Check": results["MarketCap_Check"],

                # 🔹 Volume essentials
                "Current Buys": stats["buy_usd"],
                "Current Sells": stats["sell_usd"],
                "Current Volume": stats["total_usd"],
        }

    def build_all_tokens_found_excel(self,signature:str,token_mint:str,liquidity:float,market_cap:float):
        return{
        "Timestamp": self._get_formatted_date_str(),
        "Signature": signature,
        "Token Mint": token_mint,
        "Liquidity (Estimated)": liquidity,
        "MarketCap": market_cap,
        }   
    
    def build_pda_excel(self,token_mint:str,pool_address:str,dex:str,migration_flag:str):
        return{
        "Token Mint": token_mint,
        "pair_key": pool_address,
        "pool_dex": dex,
        "status": migration_flag,
        }   
    
    def save_pool_pda(self,data):
        self.save_to_csv(self.BACKTEST_DIR, f"Pair_keys.csv", data)
               
    def save_post_buy(self,data):
        self.save_to_csv(self.BACKTEST_DIR, f"post_buy_checks.csv", data)
    
    def save_all_tokens(self,data):
        self.save_to_csv(self.TOKENS_DIR, f"all_tokens_found_{self._get_date_str()}.csv", data)

    def build_snapshot_volume_launch(self,token_mint:str,timestamp:int,first_trade_usd:float,signature:str):
        return{
        "Token Mint": token_mint,
        "Launch Timestamp": timestamp,
        "Launch Volume": first_trade_usd,
        "First Signature": signature,
        }

    def build_closed_data(self,token_mint:str,buy_signature:str,entry_price_usd:float,buy_time:float,pnl:float,current_price_usd:float,trigger:str):
        return{
                "Token_Addres":token_mint,
                "Buy_Signature": buy_signature,
                "Sell_Signature": "SIMULATED_SELL",
                "Buy_Timestamp": buy_time,
                "Sell_Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "Entry_USD": entry_price_usd,
                "Exit_USD": current_price_usd,
                "PnL (%)": pnl,
                "Trigger": trigger,
            }
    
    def save_closed_poistions(self,data:dict,sim:bool):
         self.save_to_csv(self.CLOSED_POISTIONS, f"simulated_closed_positions.csv"if sim else "closed_positions.csv", data)

    def finalize_trade(self, signature: str, trade_type: str, exit_usd: float = None,sim: bool = False) -> None:
        if sim:

            open_file = os.path.join(self.OPEN_POISTIONS, f"simulated_tokens.csv")
            closed_file = os.path.join(self.CLOSED_POISTIONS, f"simulated_closed_positions.csv")
        else:
            open_file = os.path.join(self.OPEN_POISTIONS, f"open_positions.csv")
            closed_file = os.path.join(self.CLOSED_POISTIONS, f"closed_positions.csv")

        if not os.path.exists(open_file):
            logger.warning(f"⚠️ Open positions file missing, cannot finalize {signature}")
            return

        df = pd.read_csv(open_file)

        if trade_type.upper() == "BUY":
            col = "Buy_Signature"
            final_status = "SIMULATED_BUY" if sim else "BOUGHT"
        elif trade_type.upper() == "SELL":
            col = "Sell_Signature"
            final_status = "SIMULATED_SELL" if sim else "SOLD"
        else:
            logger.error(f"❌ Unknown trade_type '{trade_type}' for signature {signature}")
            return

        if col not in df.columns:
            logger.warning(f"⚠️ File missing '{col}' column, cannot finalize {signature}")
            return

        mask = df[col] == signature
        if not mask.any():
            logger.warning(f"⚠️ No matching pending {trade_type} found for {signature}")
            return

        df.loc[mask, "type"] = final_status
        df.loc[mask, f"{trade_type.capitalize()}_Timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if trade_type.upper() == "SELL":
            if exit_usd is not None:
                df.loc[mask, "Exit_USD"] = exit_usd

            if "Entry_USD" in df.columns and "Exit_USD" in df.columns:
                try:
                    entry_usd = df.loc[mask, "Entry_USD"].astype(float)
                    final_exit_usd = df.loc[mask, "Exit_USD"].astype(float)
                    df.loc[mask, "PnL_%"] = ((final_exit_usd.values / entry_usd.values) - 1) * 100
                except Exception as e:
                    logger.warning(f"⚠️ Failed to compute PnL% for {signature}: {e}")

        df_remaining = df[~mask]
        df_remaining.to_csv(open_file, index=False)

        df[mask].to_csv(
            closed_file,
            mode="a",
            header=not os.path.exists(closed_file),
            index=False
        )

        logger.info(
    f"📊 Finalized {trade_type.upper()} written to "
    f"{'simulated_' if sim else ''}closed_positions for {signature}"
)

    def save_volume_snapshot(self,data):
        self.save_to_csv(self.BACKTEST_DIR, f"token_volume.csv", data)
   
    def log_for_ui(self, sim) -> list[dict]:
        if sim:
            closed_file = os.path.join(self.CLOSED_POISTIONS, f"simulated_closed_positions.csv")
        else:
            closed_file = os.path.join(self.CLOSED_POISTIONS, f"closed_positions.csv")

        if not os.path.exists(closed_file):
            logger.debug("📭 No closed positions file yet.")
            return []

        df = pd.read_csv(closed_file)
        logs = []

        for _, row in df.iterrows():
            logs.append({
                "event": row.get("type", "").lower(),
                "signature": row.get("Sell_Signature") or row.get("Buy_Signature"),
                "token_mint": row.get("Token_bought"),
                "input_mint": row.get("Token_sold"),
                "pnl": float(row.get("PnL_%", 0)) if "PnL_%" in row else None,
            })

        return logs
    
    def save_liquidity(self,data)->None:
        self.save_to_csv(self.BACKTEST_DIR, f"liquidty.csv",data)
   
    def build_liquidity_csv(self, token_mint: str, breakdown: dict) -> dict:
        return {
            "Token Address": token_mint,
            "SOL_LIQ": breakdown.get("SOL", 0.0),
            "USDC_LIQ": breakdown.get("USDC", 0.0),
            "USDT_LIQ": breakdown.get("USDT", 0.0),
            "USD1_LIQ": breakdown.get("USD1", 0.0),
            "OTHERS_LIQ": breakdown.get("OTHERS", 0.0),
            "TOTAL_LIQ": sum(breakdown.values())-breakdown.get("OTHERS", 0.0),
        }

    def load_pool_pdas(self, filename: str = "Pair_keys.csv") -> dict[str, dict]:
        filepath = os.path.join(self.BACKTEST_DIR, filename)
        if not os.path.exists(filepath):
            return {}

        df = pd.read_csv(filepath)
        pools = {}
        for _, row in df.iterrows():
            pools[row["Token Mint"]] = {
                "pool": row["pair_key"],
                "dex": row.get("DEX", None)
            }
        return pools

    def update_buy(self,base_data:dict,buy_signature:str,real_entry_price:float):
        base_data.update({
            "Buy_Signature": buy_signature,
            "Real_Entry_Price": real_entry_price,
            "Entry_USD":real_entry_price
        })
        return base_data

    def update_sell(self, base_data: dict,exit_usd: float):
        base_data.update({"Exit_USD": exit_usd})
        entry_usd = base_data.get("Entry_USD")
        if entry_usd and exit_usd:
            try:
                base_data["PnL_%"] = ((exit_usd / float(entry_usd)) - 1) * 100
            except Exception:
                base_data["PnL_%"] = None

        return base_data

    def _get_date_str(self)->datetime:
        return datetime.now().strftime("%Y-%m-%d")
    
    def _get_formatted_date_str(self)->datetime:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
