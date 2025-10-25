import pandas as pd
import time
import os
from datetime import datetime
import threading
from services.bot_context import BotContext
from helpers.framework_utils import parse_timestamp




class OpenPositionTracker:
    def __init__(self,ctx:BotContext):
        #objects
        self.ctx = ctx
        self.settings = ctx.settings
        self.logger =  ctx.get("logger")
        self.tracker_logger =  ctx.get("tracker_logger")
        
        #local instances
        self.running = True
        self.base_token = "So11111111111111111111111111111111111111112"
        self.failed_sells = {}
        self.max_retries = 3
        self.tokens_to_remove = set()
        self.tokens_lock = threading.Lock()
        self.peak_price_dict = {}
        self.token_name_cache = {}
        self.token_image_cache = {}
        self.buy_timestamp = {}


        
        #check bot mode
        self.file_path = os.path.join(
            ctx.get("excel_utility").OPEN_POISTIONS,
            f"simulated_tokens.csv" if  self.settings["SIM_MODE"] else f"open_positions.csv"
        )
        self.exit_checks = {
        "USE_SL": self.check_emergency_sl,       
        "USE_TP": self.check_take_profit,        
        "USE_TSL": self.check_trailing_stop,    
        "USE_TIMEOUT": self.check_timeout,       
    }

    def track_positions(self, stop_event):
        self.logger.info("📚 Starting to track open positions from Excel...")

        while not stop_event.is_set() or self.has_open_positions():
            if not os.path.exists(self.file_path):
                self.logger.debug("📭 Waiting for buy file to be created...")
                time.sleep(1)
                continue

            try:
                df = pd.read_csv(self.file_path)
                if df.empty:
                    self.logger.debug("📭 File is empty.")
                    time.sleep(5)
                    continue

                required_columns = {"Token_bought", "Token_sold", "Quote_Price", "type", "Real_Entry_Price", "Buy_Timestamp"}
                if not required_columns.issubset(df.columns):
                    self.logger.info("📄 File missing expected columns — waiting...")
                    time.sleep(1)
                    continue

                df = df[df["type"].isin(["BOUGHT", "SIMULATED_BUY"])]
                token_mints = df["Token_bought"].dropna().tolist()
                mints = list(set(token_mints + [self.base_token]))

                if len(mints) == 2:
                    try:
                        token_price = self.ctx.get("jupiter_client").get_token_price(token_mints[0])
                        sol_price = self.ctx.get("jupiter_client").get_token_price(self.base_token)
                        price_data = {
                            token_mints[0]: token_price,
                            self.base_token: sol_price
                        }
                    except Exception as e:
                        self.logger.warning(f"⚠️ Failed to fetch single token prices: {e}")
                        continue
                else:
                    price_data = self.ctx.get("jupiter_client").get_token_prices(mints)

                for _, row in df.iterrows():
                    token_mint = row["Token_bought"]
                    input_mint = row["Token_sold"]
                    buy_signature = row["Buy_Signature"]

                    if token_mint not in price_data or self.base_token not in price_data:
                        self.logger.warning(f"⚠️ Missing price data for {token_mint} or SOL.")
                        continue
                    if "Entry_USD" in row and not pd.isna(row["Entry_USD"]):
                        buy_price_usd = float(row["Entry_USD"])
                    else:
                        sol_price_usd = float(price_data[self.base_token])
                        buy_price_sol = float(row["Real_Entry_Price"] if not pd.isna(row["Real_Entry_Price"]) else row["Quote_Price"])
                        buy_price_usd = buy_price_sol * sol_price_usd

                    current_price_usd = float(price_data[token_mint])
                    buy_time = parse_timestamp(row["Buy_Timestamp"])
                    self.buy_timestamp[token_mint] = buy_time
                    
                    if token_mint not in self.token_name_cache or self.token_image_cache.get(token_mint) is None:
                        try:
                            metadata = self.ctx.get("helius_client").get_token_meta_data(token_mint)
                            if metadata:
                                self.token_name_cache[token_mint] = metadata.get("name", token_mint)
                                self.token_image_cache[token_mint] = metadata.get("image")
                            else:
                                self.token_name_cache[token_mint] = token_mint
                                self.token_image_cache[token_mint] = None
                        except Exception as e:
                            self.logger.debug(f"⚠️ Metadata lookup failed for {token_mint}: {e}")
                            self.token_name_cache[token_mint] = token_mint
                            self.token_image_cache[token_mint] = None

                    self.logger.info(
                        f"🔎 Tracking {token_mint} | Buy: ${buy_price_usd:.10f} | Current: ${current_price_usd:.10f}"
                    )
                    pnl = ((current_price_usd - buy_price_usd) / buy_price_usd) * 100
                    self.tracker_logger.info({
                        "event": "track",
                        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "token_mint": token_mint,
                        "input_mint":input_mint,
                        "entry_price": buy_price_usd,
                        "current_price": current_price_usd,
                        "trigger": None,
                        "pnl": pnl,
                        "token_name": self.token_name_cache.get(token_mint, token_mint),
                        "token_image": self.token_image_cache.get(token_mint),
                    })
                    
                    exit_rules = self.settings.get("EXIT_RULES", {})
                    for rule, func in self.exit_checks.items():
                        if exit_rules.get(rule, False):
                            result = func(token_mint, buy_price_usd, current_price_usd, buy_time)
                            if result:
                                trigger = result["trigger"]
                                self.logger.info(f"⚡ Exit triggered: {trigger} for {token_mint}")
                                data = self.ctx.get("excel_utility").build_closed_data(token_mint,buy_signature,buy_price_usd,buy_time,pnl,current_price_usd,trigger)
                                self.ctx.get("excel_utility").save_closed_poistions(data,self.ctx.settings["SIM_MODE"])
                                with self.tokens_lock:
                                    self.tokens_to_remove.add(token_mint)
                                if row["type"] == "SIMULATED_BUY":
                                    break
                                else:
                                    self.sell_and_update(token_mint, input_mint)
                                    break

                with self.tokens_lock:
                    if self.tokens_to_remove:
                        df = df[~df["Token_bought"].isin(self.tokens_to_remove)]
                        df.to_csv(self.file_path, index=False)
                        self.logger.info(f"🧼 Removed {len(self.tokens_to_remove)} tokens from open positions.")
                        self.tokens_to_remove.clear()

            except Exception as e:
                self.logger.error(f"❌ Error in OpenPositionTracker: {e}")

            time.sleep(0.25)

    def sell_and_update(self, token_mint:str, input_mint:str):
        try:
            sell_signature = self.ctx.get("trader").sell(token_mint, input_mint)     
            if not sell_signature:
                self.logger.warning(f"❌ Sell failed for {token_mint}. Will retry.")
                if token_mint not in self.failed_sells:
                    self.failed_sells[token_mint] = {"input_mint": input_mint, "retries": 1}
                else:
                    self.failed_sells[token_mint]["retries"] += 1
                return
            self.logger.info(f"📨 Sell submitted for {token_mint}  signature={sell_signature}")

        except Exception as e:
            self.logger.error(f"❌ Exception in sell_and_update for {token_mint}: {e}")
            if token_mint not in self.failed_sells:
                self.failed_sells[token_mint] = {"input_mint": input_mint, "retries": 1}
            else:
                self.failed_sells[token_mint]["retries"] += 1

    def has_open_positions(self):
            try:
                if not os.path.exists(self.file_path):
                    return False

                df = pd.read_csv(self.file_path)
                df = df[df["type"].isin(["BOUGHT", "SIMULATED_BUY"])]
                return not df.empty

            except Exception as e:
                self.logger.error(f"❌ Error checking open positions: {e}")
                return True 

    def check_take_profit(self, token_mint:str, buy_price_usd:float, current_price_usd:float, buy_time):
        tp = self.settings.get("TP", 2.0)
        if current_price_usd >= buy_price_usd * tp:
            return {"trigger": "TP"}
        return None

    def check_trailing_stop(self, token_mint:str, buy_price_usd:float, current_price_usd:float, buy_time):
        sl = self.settings.get("TRAILING_STOP", 0.2)
        min_trigger = self.settings.get("MIN_TSL_TRIGGER_MULTIPLIER", 1.15)

        peak_price = self.peak_price_dict.get(token_mint, buy_price_usd)
        if current_price_usd > peak_price:
            self.peak_price_dict[token_mint] = current_price_usd

        if peak_price >= buy_price_usd * min_trigger:
            trailing_stop = peak_price * (1 - sl)
            if current_price_usd <= trailing_stop:
                return {"trigger": "TSL"}
        return None

    def check_emergency_sl(self, token_mint:str, buy_price_usd:float, current_price_usd:float, buy_time):
        emergency_sl = self.settings.get("SL", 0.1)
        # Only if token has NOT pumped yet
        peak_price = self.peak_price_dict.get(token_mint, buy_price_usd)
        has_pumped = peak_price >= buy_price_usd * self.settings.get("MIN_TSL_TRIGGER_MULTIPLIER", 1.5)
        if not has_pumped and current_price_usd <= buy_price_usd * (1 - emergency_sl):
            return {"trigger": "SL"}
        return None

    def check_timeout(self, token_mint:str, buy_price_usd:float, current_price_usd:float, buy_time):
            timeout = self.settings.get("TIMEOUT_SECONDS", 30)
            threshold = self.settings.get("TIMEOUT_PROFIT_THRESHOLD", 1.2)

            try:
                seconds_since = (datetime.now() - buy_time).total_seconds()
                if seconds_since > timeout and current_price_usd < buy_price_usd * threshold:
                    return {"trigger": "TIMEOUT"}
            except Exception as e:
                self.logger.warning(f"⚠️ Could not parse Timestamp for timeout check: {e}")
            return None
    
