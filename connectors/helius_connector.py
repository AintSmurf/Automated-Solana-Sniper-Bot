import time
import json
import os
import logging
import websocket
from utilities.credentials_utility import CredentialsUtility
from utilities.excel_utility import ExcelUtility
from utilities.requests_utility import RequestsUtility
from config.urls import HELIUS_URL
from config.web_socket import HELIUS

# Setup logging
LOG_FILE = "helius_sniper.log"
LOG_FORMAT = "%(asctime)s - %(levelname)s - %(message)s"
logging.basicConfig(
    filename=LOG_FILE, filemode="a", format=LOG_FORMAT, level=logging.INFO
)
logger = logging.getLogger()

# Also log to console
console_handler = logging.StreamHandler()
console_handler.setFormatter(logging.Formatter(LOG_FORMAT))
logger.addHandler(console_handler)

# Global storage for new signatures
signature_queue = []


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

    def fetch_and_save_transaction(self, signature):
        """Fetch transaction details and save to CSV."""
        logger.info(f"Fetching transaction details for: {signature}")
        self.transaction_payload["params"][0] = signature
        self.transaction_payload["id"] = self.id
        self.id += 1

        try:
            tx_data = self.requests_utility.post(payload=self.transaction_payload)

            # Log raw response for debugging
            logger.info(f"🔍 Raw transaction data: {json.dumps(tx_data, indent=4)}")

            # Extract relevant data safely
            result = tx_data.get("result", {})
            meta = result.get("meta", {})
            transaction = result.get("transaction", {})

            # Signature
            extracted_signature = transaction.get("signatures", ["N/A"])[0]

            # Balances
            pre_balance = meta.get("preBalances", [0])[0]
            post_balance = meta.get("postBalances", [0])[0]

            # Instructions (if needed)
            instructions = transaction.get("message", {}).get("instructions", [])
            first_instruction = instructions[0] if instructions else {}

            # Save to Excel
            self.excel_utility.save_to_csv(
                "TRANSACTIONS_DIR",
                "transactions.csv",
                {
                    "Signature": [extracted_signature],
                    "Pre-Balance": [pre_balance],
                    "Post-Balance": [post_balance],
                    "Instruction Data": [first_instruction.get("data", "N/A")],
                },
            )

        except Exception as e:
            logger.error(f"❌ Error fetching/saving transaction details: {e}")

    def run_transaction_fetcher(self):
        """Runs transaction fetcher every 30 seconds in a loop."""
        while True:
            time.sleep(30)
            if signature_queue:
                logger.info(
                    f"🔄 Fetching transactions for {len(signature_queue)} new signatures..."
                )
                while signature_queue:
                    signature = signature_queue.pop(0)
                    self.fetch_and_save_transaction(signature)

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
        """Handles incoming WebSocket messages."""
        try:
            data = json.loads(message)
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

            for log in logs:
                if "Instruction: Initialize" in log:
                    logger.info(f"🔵 New Pool Detected: {signature}")
                    signature_queue.append(signature)

                    # Save to CSV
                    self.excel_utility.save_to_csv(
                        self.excel_utility.SIGNATURES_DIR,
                        "pools.csv",
                        {"Signature": [signature]},
                    )

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
