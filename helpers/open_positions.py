import pandas as pd
from utilities.excel_utility import ExcelUtility
from helpers.logging_manager import LoggingHandler
import time
import os
from datetime import datetime
from helpers.solana_manager import SolanaHandler
from helpers.rate_limiter import RateLimiter
import threading

logger = LoggingHandler.get_logger()


class OpenPositionTracker:
    def __init__(self, tp: float, sl: float,rate_limiter: RateLimiter):
        self.tp = tp
        self.sl = sl
        self.excel_utility = ExcelUtility()
        self.solana_manager = SolanaHandler(rate_limiter)
        self.running = True
        self.base_token = "So11111111111111111111111111111111111111112"
        self.failed_sells = {}
        self.max_retries = 3
        self.tokens_to_remove = set()
        self.tokens_lock = threading.Lock()
        self.file_path = os.path.join(self.excel_utility.BOUGHT_TOKENS, "open_positions.csv")

    def track_positions(self):
        logger = LoggingHandler.get_logger()
        logger.info("📚 Starting to track open positions from Excel...")
        while self.running:
            if not os.path.exists(self.file_path):
                logger.debug("📭 Waiting for buy file to be created...")
                time.sleep(1)
                continue
            
            try:
                df = pd.read_csv(self.file_path)
                if df.empty:
                    logger.debug("📭 open_positions.csv is empty.")
                    time.sleep(5)
                    continue
                required_columns = {"Token_bought", "Token_sold", "Token_price", "type"}
                if not required_columns.issubset(df.columns):
                    logger.info("📄 File exists but missing expected columns — waiting...")
                    time.sleep(1)
                    continue

                df = df[df["type"] == "BUY"]
                mints = df["Token_bought"].tolist() + [self.base_token]
                price_data = self.solana_manager.get_token_prices(mints)["data"]
                logger.debug(f"price data:{price_data}")

                for idx, row in df.iterrows():
                    token_mint = row["Token_bought"]
                    input_mint = row["Token_sold"]
                    buy_price_per_token = float(row["Token_price"])

                    if token_mint not in price_data or input_mint not in price_data:
                        logger.warning(f"⚠️ Missing price data for {token_mint}")
                        continue

                    current_price = float(price_data[token_mint]["price"])

                    take_profit_price = buy_price_per_token * self.tp
                    stop_loss_price = buy_price_per_token * self.sl
                    change = ((current_price - buy_price_per_token) / buy_price_per_token) * 100


                    logger.info(
                        f"🔎 Tracking {token_mint}... Current: {current_price:.10f}, Buy: {buy_price_per_token:.10f}, change: {change:.2f}%"
                    )

                    if current_price >= take_profit_price:
                        logger.info(
                            f"🎯 TAKE PROFIT triggered for {token_mint}! Selling..."
                        )
                        self.sell_and_update(token_mint, input_mint)
                        continue

                    if current_price <= stop_loss_price:
                        logger.info(
                            f"🚨 STOP LOSS triggered for {token_mint}! Selling..."
                        )
                        self.sell_and_update(token_mint, input_mint)
                        continue
                
                with self.tokens_lock:
                    if self.tokens_to_remove:
                        df = df[~df["Token_bought"].isin(self.tokens_to_remove)]
                        df.to_csv(self.file_path, index=False)
                        logger.info(f"🧼 Removed {len(self.tokens_to_remove)} tokens from open positions.")
                        self.tokens_to_remove.clear()

            except Exception as e:
                logger.error(f"❌ Error in OpenPositionTracker: {e}")


            time.sleep(0.25)
    
    def sell_and_update(self, token_mint, input_mint):
        try:
            result = self.solana_manager.sell(token_mint, input_mint)

            if not result["success"]:
                logger.warning(f"❌ Sell failed for {token_mint}. Skipping log and update.")
                if token_mint not in self.failed_sells:
                    self.failed_sells[token_mint] = {"input_mint": input_mint, "retries": 1}
                else:
                    self.failed_sells[token_mint]["retries"] += 1
                return

            executed_price = result["executed_price"]
            signature = result.get("signature", "")

            # Load the token's original buy price from file
            try:
                current_df = pd.read_csv(self.file_path)
                matched_row = current_df[current_df["Token_bought"] == token_mint]

                if matched_row.empty:
                    logger.warning(f"⚠️ No matching entry price found for {token_mint}")
                    return

                entry_price = float(matched_row.iloc[0]["Token_price"])
            except Exception as e:
                logger.error(f"❌ Failed to read entry price for {token_mint}: {e}")
                return

            pnl = ((executed_price - entry_price) / entry_price) * 100

            data = {
                "Timestamp": [datetime.now().strftime("%Y-%m-%d %H:%M:%S")],
                "Token Mint": [token_mint],
                "Entry": [entry_price],
                "Exit": [executed_price],
                "PnL (%)": [round(pnl, 2)],
                "Signature": [signature],
                "Type": ["SOLD"]
            }

            self.excel_utility.save_to_csv(
                self.excel_utility.BOUGHT_TOKENS,
                "closed_positions.csv",
                data,
            )

            with self.tokens_lock:
                self.tokens_to_remove.add(token_mint)
            logger.info(f"✅ Sold {token_mint} | Executed: {executed_price:.8f} | PnL: {pnl:.2f}%")

        except Exception as e:
            logger.error(f"❌ Exception in sell_and_update for {token_mint}: {e}")
    
    def retry_failed_sells(self):
        while self.running:
            time.sleep(10)

            if not self.failed_sells:
                continue

            logger.info(f"🔁 Retrying {len(self.failed_sells)} failed sells...")

            to_remove = []

            for token_mint, info in list(self.failed_sells.items()):
                input_mint = info["input_mint"]
                retries = info["retries"]

                if retries > self.max_retries:
                    logger.warning(f"🚫 Max retries exceeded for {token_mint}. Giving up.")
                    self.excel_utility.save_to_csv(
                        self.excel_utility.BOUGHT_TOKENS,
                        "failed_sells.csv",
                        {
                            "Timestamp": [datetime.now().strftime("%Y-%m-%d %H:%M:%S")],
                            "Token Mint": [token_mint],
                            "Input Mint": [input_mint],
                            "Reason": ["Max retries exceeded"],
                        },
                    )
                    to_remove.append(token_mint)
                    continue  

                try:
                    self.sell_and_update(token_mint, input_mint)
                    to_remove.append(token_mint)
                except Exception as e:
                    self.failed_sells[token_mint]["retries"] += 1
                    logger.error(f"❌ Retry #{retries} failed for {token_mint}: {e}")

            for token in to_remove:
                self.failed_sells.pop(token, None)
