import time
import json
import os
import logging
import websocket
import sys
from utilities.credentials_utility import CredentialsUtility
from utilities.excel_utility import ExcelUtility
from utilities.requests_utility import RequestsUtility
from config.urls import HELIUS_URL
from config.web_socket import HELIUS


# Setup logging
LOG_FILE = "helius_sniper.log"
LOG_FORMAT = "%(asctime)s - %(levelname)s - %(message)s"

# ✅ File handler (Logs everything)
file_handler = logging.FileHandler(LOG_FILE, mode="a", encoding="utf-8")  # Use UTF-8
file_handler.setFormatter(logging.Formatter(LOG_FORMAT))
file_handler.setLevel(logging.DEBUG)  # Save all logs

# ✅ Console handler (Only logs INFO and above)
console_handler = logging.StreamHandler(sys.stdout)  # Force standard output
console_handler.setFormatter(logging.Formatter(LOG_FORMAT))
console_handler.setLevel(logging.INFO)  # Only display INFO and above in console

# ✅ Create logger
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)  # Capture all logs

# ✅ Add handlers
logger.addHandler(file_handler)
logger.addHandler(console_handler)


# Global storage for new signatures
signature_queue = []


# Global storage for new signatures
signature_queue = []

latest_block_time = int(time.time())  # Approximate current Unix timestamp
known_tokens = set()
seen_tokens = set()


class HeliusConnector:
    def __init__(self, devnet=None):
        logger.info("Initializing Helius WebSocket connection...")
        credentials_utility = CredentialsUtility()
        self.excel_utility = ExcelUtility()
        self.requests_utility = RequestsUtility(HELIUS_URL["BASE_URL"])
        self.api_key = credentials_utility.get_helius_api_key()

        if devnet:
            self.wss_url = HELIUS["LOGS_SOCKET_DEVNET"] + self.api_key["API_KEY"]
        else:
            self.wss_url = HELIUS["LOGS_SOCKET_MAINNET"] + self.api_key["API_KEY"]

        logger.info(self.wss_url)
        self.prepare_files()
        self.id = 1

    def get_payload(self, file):
        path = os.path.join(os.path.dirname(__file__), "..", "data", f"{file}.json")
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def prepare_files(self):
        self.raydium_payload = self.get_payload("Raydium")
        self.transaction_payload = self.get_payload("Transaction")

    def fetch_transaction(self, signature):
        """Fetch transaction details from Helius API."""
        logger.info(f"Fetching transaction details for: {signature}")

        # Replace placeholders in transaction payload
        self.transaction_payload["id"] = self.id
        self.transaction_payload["params"][0] = signature
        self.id += 1

        try:
            tx_data = self.requests_utility.post(
                endpoint=self.api_key["API_KEY"], payload=self.transaction_payload
            )

            # ✅ Extract Token Mint & Owner (PostTokenBalances)
            post_token_balances = (
                tx_data.get("result", {}).get("meta", {}).get("postTokenBalances", [])
            )

            token_mint = (
                post_token_balances[0]["mint"] if post_token_balances else "N/A"
            )
            token_owner = (
                post_token_balances[0]["owner"] if post_token_balances else "N/A"
            )

            # ✅ Check if token is already known
            if token_mint in known_tokens:
                logger.debug(f"⏩ Ignoring known token: {token_mint}")
                return

            # ✅ Extract Liquidity (Estimated)
            pre_balances = (
                tx_data.get("result", {}).get("meta", {}).get("preBalances", [])
            )
            post_balances = (
                tx_data.get("result", {}).get("meta", {}).get("postBalances", [])
            )

            liquidity = (
                pre_balances[0] - post_balances[0]
                if len(pre_balances) > 0 and len(post_balances) > 0
                else 0
            )

            # ✅ Market Cap Placeholder (Needs external API)
            market_cap = "N/A"

            # ✅ Save to CSV
            self.excel_utility.save_to_csv(
                self.excel_utility.TRANSACTIONS_DIR,
                "transactions.csv",
                {
                    "Signature": [signature],
                    "Token Mint": [token_mint],
                    "Token Owner": [token_owner],
                    "Liquidity (Estimated)": [liquidity],
                    "Market Cap": [market_cap],
                },
            )

            logger.info(
                f"✅ New Token Data Saved: {token_mint} (Signature: {signature})"
            )

        except Exception as e:
            logger.error(f"❌ Error fetching transaction data: {e}")

    def run_transaction_fetcher(self):
        while True:
            if signature_queue:
                logger.info(
                    f"🔄 Fetching transactions for {len(signature_queue)} new signatures..."
                )
                while signature_queue:
                    signature = signature_queue.pop(0)
                    self.fetch_transaction(signature)

    def start_ws(self):
        """Starts the WebSocket connection to Helius RPC."""
        logger.info(f"Connecting to WebSocket: {self.wss_url}")
        self.ws = websocket.WebSocketApp(
            self.wss_url,
            on_open=self.on_open,
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close,
        )
        self.ws.run_forever()

    def on_open(self, ws):
        """Subscribe to logs for new liquidity pools on Raydium AMM."""
        logger.info("WebSocket connected. Subscribing to Raydium AMM logs...")
        self.raydium_payload["id"] = self.id
        self.id += 1
        ws.send(json.dumps(self.raydium_payload))
        logger.info("✅ Successfully subscribed to AMM liquidity logs.")

    def on_message(self, ws, message):
        """Handles incoming WebSocket messages for detecting new tokens ONLY."""
        try:
            data = json.loads(message)

            # ✅ Extract Slot and Signature
            slot = (
                data.get("params", {})
                .get("result", {})
                .get("context", {})
                .get("slot", None)
            )
            signature = (
                data.get("params", {})
                .get("result", {})
                .get("value", {})
                .get("signature", "")
            )
            logs = (
                data.get("params", {})
                .get("result", {})
                .get("value", {})
                .get("logs", [])
            )
            error = (
                data.get("params", {})
                .get("result", {})
                .get("value", {})
                .get("err", None)
            )
            pre_token_balances = (
                data.get("params", {})
                .get("result", {})
                .get("value", {})
                .get("preTokenBalances", [])
            )
            if error is not None:
                logger.debug(
                    f"⚠️ Ignoring failed transaction: {signature} (Error: {error})"
                )
                return

            if not any("Instruction: InitializeMint" in log for log in logs):
                logger.debug(f"⏩ Ignoring non-token mint transaction: {signature}")
                return
            logger.info("✅ Passed Step 1: Detected 'InitializeMint' instruction.")
            # step2
            if pre_token_balances:
                logger.debug(
                    f"⏩ Ignoring transaction (Token existed before): {signature}"
                )
                return

            logger.info(
                "✅ Passed Step 2: Token was NOT in `preTokenBalances`, likely new."
            )
            # step3

            # step4
            current_time = int(time.time())
            token_old = 30
            block_time = latest_block_time - (321794320 - slot) * 0.4

            if current_time - block_time > token_old:
                logger.warning(
                    f"⚠️ Ignoring old transaction: {signature} (Slot: {slot})"
                )
                return

            logger.info(f"✅ Passed Step 4: Transaction is within {token_old} seconds.")

            if signature in signature_queue:
                logger.debug(f"⏩ Ignoring duplicate signature: {signature}")
                return

            signature_queue.append(signature)
            logger.info(f"🎯 New Token Detected: {signature} (Slot: {slot})")

        except Exception as e:
            logger.error(f"❌ Error processing WebSocket message: {e}")

    def on_error(self, ws, error):
        """Handles WebSocket errors."""
        logger.error(f"WebSocket error: {error}")

    def on_close(self, ws, close_status_code, close_msg):
        """Handles WebSocket disconnection."""
        logger.warning("WebSocket connection closed. Reconnecting in 5s...")
        time.sleep(5)
        self.start_ws()  # Auto-reconnect
