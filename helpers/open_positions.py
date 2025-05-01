import pandas as pd
from utilities.excel_utility import ExcelUtility
from helpers.logging_manager import LoggingHandler
import time
import os
from datetime import datetime
from helpers.solana_manager import SolanaHandler

logger = LoggingHandler.get_logger()


class OpenPositionTracker:
    def __init__(self, tp: float, sl: float):
        self.tp = tp
        self.sl = sl
        self.excel_utility = ExcelUtility()
        self.solana_manager = SolanaHandler()
        self.running = True
        self.base_token = "So11111111111111111111111111111111111111112"
        self.file_path = ""

    def track_positions(self):
        logger = LoggingHandler.get_logger()
        logger.info("📚 Starting to track open positions from Excel...")
        now = datetime.now()
        date_str = now.strftime("%Y-%m-%d")
        filename = f"bought_tokens_{date_str}.csv"
        self.file_path = os.path.join(self.excel_utility.BOUGHT_TOKENS, filename)
        while self.running:
            if os.path.exists(self.file_path):
                try:
                    df = pd.read_csv(self.file_path)
                    df = df[df["type"] == "BUY"]

                    if df.empty:
                        logger.info("📭 No open positions to track.")
                        time.sleep(5)
                        continue

                    mints = df["Token boguht"].tolist() + [self.base_token]
                    price_data = self.solana_manager.get_token_prices(mints)["data"]
                    logger.debug(f"price data:{price_data}")

                    for idx, row in df.iterrows():
                        token_mint = row["Token boguht"]
                        input_mint = row["Token_sold"]
                        buy_price_per_token = float(row["Token_price"])

                        if token_mint not in price_data or input_mint not in price_data:
                            logger.warning(f"⚠️ Missing price data for {token_mint}")
                            continue

                        current_price = float(price_data[token_mint]["price"])

                        take_profit_price = buy_price_per_token * self.tp
                        stop_loss_price = buy_price_per_token * self.sl

                        logger.info(
                            f"🔎 Tracking {token_mint[:4]}... Current: {current_price:.8f}, Buy: {buy_price_per_token:.8f}"
                        )

                        if current_price >= take_profit_price:
                            logger.info(
                                f"🎯 TAKE PROFIT triggered for {token_mint}! Selling..."
                            )
                            self.sell_and_update(
                                df, idx, token_mint, input_mint, current_price
                            )
                            continue

                        if current_price <= stop_loss_price:
                            logger.info(
                                f"🚨 STOP LOSS triggered for {token_mint}! Selling..."
                            )
                            self.sell_and_update(
                                df, idx, token_mint, input_mint, current_price
                            )
                            continue

                except Exception as e:
                    logger.error(f"❌ Error in OpenPositionTracker: {e}")
                else:
                    continue

            time.sleep(5)

    def sell_and_update(self, df, idx, token_mint, input_mint, sell_price):
        try:
            # Perform sell
            self.solana_manager.sell(token_mint, input_mint)
            df.at[idx, "type"] = "SOLD"
            df.at[idx, "Sold_At_Price"] = sell_price
            df.to_csv(self.file_path, index=False)
        except Exception as e:
            logger.error(f"❌ Error selling token: {e}")
