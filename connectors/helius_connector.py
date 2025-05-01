import time
import json
import websocket
from datetime import datetime
from utilities.credentials_utility import CredentialsUtility
from utilities.excel_utility import ExcelUtility
from utilities.requests_utility import RequestsUtility
from helpers.logging_manager import LoggingHandler
from helpers.solana_manager import SolanaHandler
from helpers.framework_manager import get_payload
from config.urls import HELIUS_URL
from config.web_socket import HELIUS
from collections import deque
from utilities.rug_check_utility import RugCheckUtility
import threading


# set up logger
logger = LoggingHandler.get_logger()

# Track processed signatures to avoid duplicates
signature_queue = deque(maxlen=500)
signature_cache = deque(maxlen=5000)

latest_block_time = int(time.time())
known_tokens = set()


class HeliusConnector:
    def __init__(self, devnet=False, API=None):
        logger.info("Initializing Helius WebSocket connection...")
        credentials_utility = CredentialsUtility()
        self.rug_utility = RugCheckUtility()
        self.excel_utility = ExcelUtility()
        self.solana_manager = SolanaHandler()
        self.requests_utility = RequestsUtility(HELIUS_URL["BASE_URL"])
        self.api_key = credentials_utility.get_helius_api_key()
        self.latest_block_time = int(time.time())
        if devnet:
            self.wss_url = HELIUS["LOGS_SOCKET_DEVNET"] + self.api_key["API_KEY"]
        else:
            self.wss_url = HELIUS["LOGS_SOCKET_MAINNET"] + self.api_key["API_KEY"]

        logger.info(self.wss_url)
        self.prepare_files()
        self.id = 1

    def prepare_files(self) -> None:
        self.raydium_payload = get_payload("Raydium")
        self.transaction_payload = get_payload("Transaction")
        self.transaction_simulation_payload = get_payload("Transaction_Simulation")
        self.token_address_payload = get_payload("Token_adress_payload")
        self.lastest_slot_paylaod = get_payload("Slot_payload")

    def fetch_transaction(self, signature: str):
        """Fetch transaction details from Helius API."""
        logger.info(f"Fetching transaction details for: {signature}")

        self.transaction_payload["id"] = self.id
        self.transaction_payload["params"][0] = signature
        self.id += 1

        try:
            tx_data = self.requests_utility.post(
                endpoint=self.api_key["API_KEY"], payload=self.transaction_payload
            )
            post_token_balances = (
                tx_data.get("result", {}).get("meta", {}).get("postTokenBalances", [])
            )

            token_mint = (
                post_token_balances[0]["mint"] if post_token_balances else "N/A"
            )
            token_owner = (
                post_token_balances[0]["owner"] if post_token_balances else "N/A"
            )
            logs = tx_data.get("result", {}).get("meta", {}).get("logMessages", [])

            logger.debug(f"transaction response:{tx_data}")
            if not token_mint:
                logger.warning(
                    f"⚠️ No valid token mint found for transaction: {signature}"
                )
                return
            # Check if the token was minted before this transaction
            if not self.is_new_token(token_mint):
                logger.info(
                    f"⏩ Ignoring token {token_mint}: Already minted before this transaction."
                )
                return

            logger.info(f"✅ Passed Step 4: Token {token_mint} is newly minted.")

            if token_mint in known_tokens:
                logger.debug(f"⏩ Ignoring known token: {token_mint}")
                return

            if token_mint == "So11111111111111111111111111111111111111112":
                logger.info("⏩ Ignoring transaction: This is a SOL transaction.")
                return
            # check liquidity
            now = datetime.now()
            date_str = now.strftime("%Y-%m-%d")
            time_str = now.strftime("%H:%M:%S")
            liquidity = self.solana_manager.analyze_liquidty(logs, token_mint)
            market_cap = "N/A"
            if liquidity > 2000:
                logger.info(
                    f"🚀 LIQUIDITY passed: ${liquidity:.2f} — considering buy for {token_mint}"
                )
                known_tokens.add(token_mint)
                # Simulated BUY (replace this with real buy() when ready)
                logger.info(f"🧪 [SIM MODE] Would BUY {token_mint} with $25")

                # Save to all_tokens_found.csv regardless
                self.excel_utility.save_to_csv(
                    self.excel_utility.TOKENS_DIR,
                    "all_tokens_found.csv",
                    {
                        "Timestamp": [f"{date_str} {time_str}"],
                        "Signature": [signature],
                        "Token Mint": [token_mint],
                        "Liquidity (Estimated)": [liquidity],
                    },
                )

                # ✅ Launch post-buy safety check thread
                threading.Thread(
                    target=self.solana_manager.post_buy_safety_check,
                    args=(token_mint, token_owner, signature, liquidity, market_cap),
                    daemon=True,
                ).start()

            else:
                logger.info("⛔ Liquidity too low — skipping.")

        except Exception as e:
            logger.error(f"❌ Error fetching transaction data: {e}")

    def run_transaction_fetcher(self):
        while True:
            if not signature_queue:
                time.sleep(0.5)
                continue

            logger.info(
                f"🔄 Fetching transactions for {len(signature_queue)} new signatures..."
            )

            while signature_queue:
                try:
                    signature = signature_queue.pop()
                    self.fetch_transaction(signature)
                except IndexError:
                    logger.warning("⚠️ Attempted to pop from an empty signature queue.")
                    break

    def start_ws(self) -> None:
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

    def on_open(self, ws) -> None:
        """Subscribe to logs for new liquidity pools on Raydium AMM."""
        logger.info("Subscribing to Raydium AMM logs...")
        self.raydium_payload["id"] = self.id
        self.id += 1
        ws.send(json.dumps(self.raydium_payload))
        logger.info("✅ Successfully subscribed to AMM liquidity logs.")

    def on_message(self, ws, message) -> None:
        """Handles incoming WebSocket messages for detecting new Raydium and Pump.fun tokens on Solana."""
        try:
            if not message:
                logger.error("❌ Received an empty WebSocket message.")
                return

            try:
                data = json.loads(message)
            except json.JSONDecodeError as e:
                logger.error(f"❌ Error decoding WebSocket message: {e}")
                return

            # Extract transaction details
            result = data.get("params", {}).get("result", {})
            context = result.get("context", {})
            value = result.get("value", {})
            slot = context.get("slot")
            signature = value.get("signature", "")
            logs = value.get("logs", [])
            error = value.get("err", None)
            block_time = value.get("blockTime", None)

            logger.debug(f"weboscket response:{data}")

            # Analyze error (if exists)
            if error is not None:
                if isinstance(error, dict) and "InstructionError" in error:
                    instr_err = error["InstructionError"][1]
                    if isinstance(instr_err, dict):
                        custom_code = instr_err.get("Custom", None)
                    else:
                        custom_code = instr_err
                    hex_code = (
                        hex(custom_code) if isinstance(custom_code, int) else "N/A"
                    )
                    logger.debug(
                        f"⚠️ TX failed with custom error {custom_code} (hex: {hex_code})"
                    )
            else:
                logger.debug(f"⚠️ TX failed with non-custom error: {error}")

            # Skip the TX only if it didn't actually try to mint
            mint_initialized = any(
                "Instruction: InitializeMint" in log
                or "Instruction: InitializeMint2" in log
                for log in logs
            )
            mint_to_executed = any("Instruction: MintTo" in log for log in logs)

            if not (mint_initialized and mint_to_executed):
                logger.debug("⛔ Skipping failed TX with no mint activity.")
                return

            # Check for duplicate
            if signature in signature_cache:
                return
            signature_cache.append(signature)

            logger.info("✅ Passed Step 1: Mint instruction found.")

            # # Step 2: Check if the transaction is recent
            current_time = int(time.time())
            if block_time:
                if (current_time - block_time) > 30:
                    logger.warning(
                        f"⚠️ Ignoring old transaction: {signature} (BlockTime: {block_time})"
                    )
                    return
            else:
                latest_slot = self.get_latest_slot()
                if (latest_slot - slot) * 0.4 > 30:  # Approximate fallback
                    logger.warning(
                        f"⚠️ Ignoring old transaction: {signature} (Slot: {slot})"
                    )
                    return
            logger.info("✅ Passed Step 2: Transaction is within 30 seconds.")

            # Step 3: Ignore duplicates from queue
            if signature in signature_queue:
                logger.debug(f"⏩ Ignoring duplicate signature from queue: {signature}")
                return
            logger.info(f"✅ Passed Step 3: Unique new token detected: {signature}")
            signature_queue.append(signature)

        except Exception as e:
            logger.error(f"❌ Error processing WebSocket message: {e}", exc_info=True)

    def on_error(self, ws, error) -> None:
        """Handles WebSocket errors."""
        logger.error(f"WebSocket error: {error}")

    def on_close(self, ws, close_status_code, close_msg) -> None:
        """Handles WebSocket disconnection."""
        logger.warning("WebSocket connection closed. Reconnecting in 5s...")
        time.sleep(5)
        self.start_ws()  # Auto-reconnect

    def is_new_token(self, mint_address: str) -> bool:
        """Check if a token is newly minted within the last 30 seconds using blockTime if available."""
        self.token_address_payload["id"] = self.id
        self.id += 1
        self.token_address_payload["params"][0] = mint_address

        response = self.requests_utility.post(
            endpoint=self.api_key["API_KEY"], payload=self.token_address_payload
        )

        if "result" in response and response["result"]:
            first_tx = response["result"][-1]
            # Use blockTime if available for precise comparison
            if "blockTime" in first_tx and first_tx["blockTime"] is not None:
                current_time = int(time.time())
                return (current_time - first_tx["blockTime"]) < 30
            # Fallback: Use slot-based estimation if blockTime is missing
            oldest_tx_slot = first_tx["slot"]
            latest_slot = self.get_latest_slot()
            return (latest_slot - oldest_tx_slot) < int(40 / 0.4)

        return False

    def get_latest_slot(self):
        self.lastest_slot_paylaod["id"] = self.id
        self.id += 1
        response = self.requests_utility.post(
            endpoint=self.api_key["API_KEY"], payload=self.lastest_slot_paylaod
        )
        return response.get("result", 0)
