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
from config.dex_detection_rules import DEX_DETECTION_RULES
import random



# set up logger
logger = LoggingHandler.get_logger()

# Track processed signatures to avoid duplicates
signature_queue = deque(maxlen=500)
signature_cache = deque(maxlen=20000)

#to clear
signature_to_token_mint = {}


latest_block_time = int(time.time())
known_tokens = set()
MAX_TOKEN_AGE_SECONDS = 180
MIN_TOKEN_LIQUIDITY = 1000


class HeliusConnector:
    def __init__(self, devnet=False, API=None):
        logger.info("Initializing Helius WebSocket connection...")
        credentials_utility = CredentialsUtility()
        self.rug_utility = RugCheckUtility()
        self.excel_utility = ExcelUtility()
        self.solana_manager = SolanaHandler()
        self.requests_utility = RequestsUtility(HELIUS_URL["BASE_URL"])
        self.api_key = credentials_utility.get_helius_api_key()
        self.dex_name = credentials_utility.get_dex()["DEX"]
        self.latest_block_time = int(time.time())
        self.rpc_call_counter = 0
        self.last_rpc_log_time = time.time()
        if devnet:
            self.wss_url = HELIUS["LOGS_SOCKET_DEVNET"] + self.api_key["API_KEY"]
        else:
            self.wss_url = HELIUS["LOGS_SOCKET_MAINNET"] + self.api_key["API_KEY"]

        logger.info(self.wss_url)
        self.prepare_files()
        self.id = 1

    def prepare_files(self) -> None:
        self.dex_payload = get_payload(self.dex_name)
        self.transaction_payload = get_payload("Transaction")
        self.transaction_simulation_payload = get_payload("Transaction_simulation")
        self.token_address_payload = get_payload("Token_adress_payload")
        self.lastest_slot_paylaod = get_payload("Slot_payload")

    def fetch_transaction(self, signature: str, tx_data=None):
        logger.info(f"Fetching transaction details for: {signature}")
        start_time = time.time()

        if tx_data is None:
            self.transaction_payload["id"] = self.id
            self.transaction_payload["params"][0] = signature
            self.id += 1

            try:
                tx_data = self.requests_utility.post(
                    endpoint=self.api_key["API_KEY"], payload=self.transaction_payload
                )
                self.rpc_call_counter += 1
                self._log_rpc_usage()
            except Exception as e:
                logger.error(f"❌ Error fetching transaction data: {e}")
                return
        try:
            results = tx_data.get("result", {})
            post_token_balances = results.get("meta", {}).get("postTokenBalances", [])

            if not post_token_balances or "mint" not in post_token_balances[0]:
                logger.warning(f"⚠️ No valid token mint found for transaction: {signature}")
                return

            token_mint = post_token_balances[0]["mint"]
            token_owner = post_token_balances[0].get("owner", "N/A")

            if token_mint in [None, "N/A"]:
                logger.warning(f"⚠️ Invalid token mint for TX {signature}")
                return

            logs = results.get("meta", {}).get("logMessages", [])
            logger.debug(f"transaction response: {tx_data}")

            if token_mint == "So11111111111111111111111111111111111111112":
                logger.info("⏩ Ignoring transaction: This is a SOL transaction.")
                return

            age = self._get_token_age(token_mint)
            if age is None:
                logger.warning(f"⚠️ Could not determine mint age for {token_mint}, skipping.")
                return

            if age > MAX_TOKEN_AGE_SECONDS:
                logger.info(f"⏩ Token {token_mint} is too old ({age}s), skipping.")
                return

            logger.info(f"✅ Passed Step 6: Token {token_mint} is {age}s old.")

            if token_mint in known_tokens:
                logger.debug(f"⏩ Ignoring known token: {token_mint}")
                self.cleanup(token_mint)
                return

            now = datetime.now()
            date_str = now.strftime("%Y-%m-%d")
            time_str = now.strftime("%H:%M:%S")

            liquidity = self.solana_manager.analyze_liquidty(logs, token_mint, self.dex_name, results)
            market_cap = "N/A"

            if liquidity > MIN_TOKEN_LIQUIDITY:
                logger.info(f"🚀 LIQUIDITY passed: ${liquidity:.2f} — considering buy for {token_mint}")
                known_tokens.add(token_mint)
                logger.info(f"🧪 [SIM MODE] Would BUY {token_mint} with $25")

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

                scam_safe = self.solana_manager.check_scam_functions_helius(token_mint)
                if not scam_safe:
                    logger.warning(f"❌ Scam check failed — skipping {token_mint}")
                    self.cleanup(token_mint)
                    return

                self.excel_utility.save_to_csv(
                    self.excel_utility.TOKENS_DIR,
                    f"bought_tokens_{date_str}.csv",
                    {
                        "Timestamp": [f"{date_str} {time_str}"],
                        "Signature": [signature],
                        "Token Mint": [token_mint],
                        "Liquidity (Estimated)": [liquidity],
                    },
                )
                elapsed = time.time() - start_time
                logger.info(f"⏱️ Finished processing {signature} in {elapsed:.2f}s")
                threading.Thread(
                    target=self.solana_manager.post_buy_safety_check,
                    args=(token_mint, token_owner, signature, liquidity, market_cap),
                    daemon=True,
                ).start()

            else:
                logger.info("⛔ Liquidity too low — skipping.")

        except Exception as e:
            logger.error(f"❌ Error processing transaction logic: {e}", exc_info=True)

    def run_transaction_fetcher(self):
        while True:
            if not signature_queue:
                time.sleep(2)
                continue

            logger.info(
                f"🔄 Fetching transactions for {len(signature_queue)} new signatures..."
            )

            while signature_queue:
                try:
                    item = signature_queue.popleft()

                    if isinstance(item, tuple):
                        signature, tx_data = item
                    else:
                        signature = item
                        tx_data = None

                    self.fetch_transaction(signature, tx_data)
                    time.sleep(random.uniform(0.10, 0.14))
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
        """Subscribe to logs for new liquidity pools on solana."""
        logger.info(f"Subscribing to {self.dex_name} AMM logs...")
        self.dex_payload["id"] = self.id
        self.id += 1
        ws.send(json.dumps(self.dex_payload))
        logger.info("✅ Successfully subscribed to liquidity logs.")

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

            logger.debug(f"websocket response: {data}")

            # Analyze error (if exists)
            if error is not None:
                if isinstance(error, dict) and "InstructionError" in error:
                    instr_err = error["InstructionError"][1]
                    if isinstance(instr_err, dict):
                        custom_code = instr_err.get("Custom", None)
                    else:
                        custom_code = instr_err
                    hex_code = hex(custom_code) if isinstance(custom_code, int) else "N/A"
                    logger.debug(
                        f"⚠️ TX failed with custom error {custom_code} (hex: {hex_code})"
                    )
            else:
                logger.debug(f"⚠️ TX failed with non-custom error: {error}")

            detection_rules = DEX_DETECTION_RULES.get(self.dex_name, [])
            mint_related = any(
                any(rule in log for rule in detection_rules)
                for log in logs
            )

            if not mint_related:
                logger.debug(f"⛔ Skipping TX: No {self.dex_name} launch indicators found.")
                return
            if signature in signature_cache:
                return
            signature_cache.append(signature)

            logger.info("✅ Passed Step 1: Mint instruction found.")

            # Step 2: Check if the transaction is recent
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

            # Step 4: Fetch transaction data (just once)
            tx_data = self.get_transaction_data(signature)
            if not tx_data:
                logger.warning(f"❌ Could not fetch transaction data for: {signature}")
                return

            post_token_balances = tx_data.get("result", {}).get("meta", {}).get("postTokenBalances", [])
            if not post_token_balances:
                logger.warning(f"❌ Token mint not found in transaction: {signature}")
                return

            token_mint = post_token_balances[0].get("mint", "N/A")
            if token_mint == "N/A" or token_mint is None:
                logger.warning(f"❌ Invalid token mint from TX: {signature}")
                return

            logger.info(f"✅ Passed Step 4: Found token address: {token_mint}")
            # Step 5: Add to queue with tx_data and save temporary for later to use the token address
            signature_to_token_mint[signature] = token_mint
            signature_queue.append((signature, tx_data))

            # Step 6: Prefetch recent txs for the same token
            try:
                txs = self.get_recent_transactions_for_token(token_mint)[1:6]
                if txs:
                    logger.info(f"📦 Found {len(txs)} early txs after mint — pre-queuing...")
                else:
                    return
                for tx_sig in txs:
                    if tx_sig in signature_cache:
                        continue
                    signature_cache.append(tx_sig)
                    signature_queue.appendleft(tx_sig)
                    logger.debug(f"🧊 Queued early tx: {tx_sig}")
            except Exception as e:
                logger.error(f"❌ Failed to prefetch txs for {signature}: {e}")

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

    def get_latest_slot(self):
        self.lastest_slot_paylaod["id"] = self.id
        self.id += 1
        response = self.requests_utility.post(
            endpoint=self.api_key["API_KEY"], payload=self.lastest_slot_paylaod
        )
        self.rpc_call_counter += 1
        self._log_rpc_usage()
        return response.get("result", 0)

    def _get_token_age(self, mint_address: str) -> int | None:
        """Returns age of the mint in seconds. If fails, returns None."""
        try:
            self.token_address_payload["id"] = self.id
            self.id += 1
            self.token_address_payload["params"][0] = mint_address

            response = self.requests_utility.post(
                endpoint=self.api_key["API_KEY"],
                payload=self.token_address_payload
            )

            if "result" in response and response["result"]:
                first_tx = response["result"][-1]
                if "blockTime" in first_tx and first_tx["blockTime"]:
                    return int(time.time()) - int(first_tx["blockTime"])
        except Exception as e:
            logger.error(f"❌ Error fetching token age: {e}")
        return None
    
    def get_recent_transactions_for_token(self, token_mint: str) -> list[str]:
        try:
            self.token_address_payload["id"] = self.id
            self.id += 1
            self.token_address_payload["params"][0] = token_mint

            response = self.requests_utility.post(
                endpoint=self.api_key["API_KEY"],
                payload=self.token_address_payload
            )

            txs = response.get("result", [])
            logger.debug(f"pulled transactions:{txs}")
            self.rpc_call_counter += 1
            self._log_rpc_usage()
            return [tx.get("signature") for tx in txs if "signature" in tx]
        except Exception as e:
            logger.error(f"❌ Failed to fetch recent TXs for token {token_mint}: {e}")
            return []
    
    def get_transaction_data(self, signature: str) -> str | None:
        try:
            self.transaction_payload["id"] = self.id
            self.transaction_payload["params"][0] = signature
            self.id += 1

            response = self.requests_utility.post(
                endpoint=self.api_key["API_KEY"], payload=self.transaction_payload
            )
            self.rpc_call_counter += 1
            self._log_rpc_usage()
            return response
        except Exception as e:
            logger.error(f"❌ Error resolving mint for TX {signature}: {e}")
        return None

    def cleanup(self,token_mint):
        signature_queue_copy = list(signature_queue)
        signature_queue.clear()
        for sig in signature_queue_copy:
            mint = signature_to_token_mint.get(sig)
            if mint != token_mint:
                signature_queue.append(sig)
        removed = 0
        for sig, mint in list(signature_to_token_mint.items()):
            if mint == token_mint:
                signature_to_token_mint.pop(sig, None)
                removed += 1
        logger.info(f"🧹 Cleaned up {removed} signatures for token {token_mint}")

    def _log_rpc_usage(self):
        now = time.time()
        if now - self.last_rpc_log_time >= 60: 
            logger.info(f"📊 RPC calls used in the last minute: {self.rpc_call_counter}")
            self.last_rpc_log_time = now
            self.rpc_call_counter = 0
