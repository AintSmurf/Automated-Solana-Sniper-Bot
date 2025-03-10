import threading
import time
from helpers.logging_manager import LoggingHandler
from datetime import datetime
from utilities.excel_utility import ExcelUtility
from helpers.solana_manager import SolanaHandler

# set up logger
logger = LoggingHandler.get_logger()


class LiquidityTracker:
    def __init__(self, solana_manager: SolanaHandler, excel_utility: ExcelUtility):
        self.solana_manager = solana_manager
        self.excel_utility = excel_utility
        self.tracking_tokens = {}
        self.lock = threading.Lock()

    def track_token(self, token_mint: str, initial_liquidity: float):
        """Starts a separate thread to monitor liquidity for a token."""
        if token_mint in self.tracking_tokens:
            return  # Already tracking this token

        with self.lock:
            self.tracking_tokens[token_mint] = initial_liquidity

        thread = threading.Thread(
            target=self._monitor_liquidity,
            args=(token_mint, initial_liquidity),
            daemon=True,
        )
        thread.start()

    def _monitor_liquidity(self, token_mint: str, initial_liquidity: float):
        """Continuously checks liquidity for a token to detect rug pulls."""
        logger.info(f"🚀 Monitoring liquidity for {token_mint}...")

        while True:
            try:
                current_liquidity = self.solana_manager.get_liqudity(token_mint)

                if current_liquidity == 0:
                    logger.warning(
                        f"⚠️ Rug Pull Detected! {token_mint} liquidity dropped to 0!"
                    )
                    self._save_rug_pull(token_mint, "Liquidity dropped to 0")
                    break

                if current_liquidity < initial_liquidity * 0.2:
                    logger.warning(
                        f"⚠️ Possible Rug Pull! {token_mint} liquidity dropped by 80%!"
                    )
                    self._save_rug_pull(token_mint, "Liquidity dropped by 80%")
                    break

                time.sleep(5)

            except Exception as e:
                logger.error(f"❌ Error monitoring liquidity for {token_mint}: {e}")
                break

        with self.lock:
            del self.tracking_tokens[token_mint]

    def _save_rug_pull(self, token_mint, reason):
        """Save rug pull alerts to a CSV file."""
        now = datetime.now()
        date_str = now.strftime("%Y-%m-%d %H:%M:%S")
        filename = "rug_pull_alerts.csv"

        self.excel_utility.save_to_csv(
            self.excel_utility.TOKENS_DIR,
            filename,
            {
                "Timestamp": [date_str],
                "Token Mint": [token_mint],
                "Alert": [reason],
            },
        )

        logger.info(f"📉 Rug Pull Alert Logged: {token_mint} | {reason}")
