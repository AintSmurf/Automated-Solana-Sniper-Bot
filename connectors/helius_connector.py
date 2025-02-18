from config.web_socket import HELIUS
from utilities.credentials_utility import CredentialsUtility
import logging
import websocket
import threading
import json
import os

# import Raydium.json
raydium_path = os.path.join(os.path.dirname(__file__), "..", "data", "Raydium.json")
with open(raydium_path, "r", encoding="utf-8") as f:
    json_data = json.load(f)


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


class HeliusConnector:
    def __init__(self, devnet=None):
        logger.info("Initializing Helius WebSocket connection...")
        credentials_utility = CredentialsUtility()
        self.api_key = credentials_utility.get_helius_api_key()
        if devnet:
            self.wss_url = HELIUS["LOGS_SOCKET_DEVNET"] + self.api_key["API_KEY"]
        else:
            self.wss_url = HELIUS["LOGS_SOCKET_MAINNET"] + self.api_key["API_KEY"]
        logger.info(self.wss_url)
        self.id = 1
        self.ws = None
        t = threading.Thread(target=self.start_ws)
        t.daemon = True
        t.start()

    def start_ws(self):
        """Starts the WebSocket connection to Helius RPC"""
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

        subscribe_msg = json_data
        ws.send(json.dumps(subscribe_msg))
        logger.info("✅ Successfully subscribed to Raydium AMM liquidity logs.")
        self.id += 1

        ws.send(json.dumps(subscribe_msg))
        logger.info("Successfully subscribed to Raydium & Orca liquidity pool logs.")

    def on_message(self, ws, message):
        """Handles incoming WebSocket messages"""
        data = json.loads(message)
        logger.info(f"New log entry received: {data}")

        # Check for Raydium/Orca liquidity pool creations
        if "result" in data:
            log_data = data["result"]["value"]
            if "Raydium" in log_data or "Orca" in log_data:
                logger.info(f"🚀 New liquidity pool detected: {log_data}")

    def on_error(self, ws, error):
        """Handles WebSocket errors"""
        logger.error(f"WebSocket error: {error}")

    def on_close(self, ws, close_status_code, close_msg):
        """Handles WebSocket disconnection"""
        logger.warning("WebSocket connection closed. Reconnecting...")
        self.start_ws()  # Auto-reconnect
