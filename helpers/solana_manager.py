from solana.rpc.api import Client
from solana.rpc.types import TokenAccountOpts
from solders.keypair import Keypair  # type: ignore
from solders.pubkey import Pubkey  # type: ignore
from solders.transaction import VersionedTransaction  # type: ignore
from solders.message import MessageV0  # type: ignore
from solders.signature import Signature  # type: ignore
from spl.token.instructions import create_associated_token_account
from helpers.logging_manager import LoggingHandler
from utilities.credentials_utility import CredentialsUtility
from utilities.requests_utility import RequestsUtility
from utilities.excel_utility import ExcelUtility
from spl.token.instructions import get_associated_token_address
from config.urls import HELIUS_URL, JUPITER_STATION, RAYDIUM
import struct
from solana.transaction import Transaction
from config.urls import JUPITER_STATION
from helpers.framework_manager import get_payload
import base64
import math
from utilities.rug_check_utility import RugCheckUtility
import requests
from datetime import datetime
import re
from helpers.rate_limiter import RateLimiter
import time
from config.settings import get_bot_settings
from helpers.volume_tracker import VolumeTracker
from spl.token.constants import TOKEN_PROGRAM_ID as SPL_TOKEN_PROGRAM_ID
from config.dex_detection_rules import PUMPFUN_PROGRAM_ID,RAYDIUM_PROGRAM_ID,KNOWN_BASES
import threading
from config.settings import load_settings



# Set up logger
logger = LoggingHandler.get_logger()
special_logger = LoggingHandler.get_special_debug_logger()


class SolanaManager:
    def __init__(self,rate_limiter: RateLimiter):
        self.helius_requests = RequestsUtility(HELIUS_URL["BASE_URL"])
        credentials_utility = CredentialsUtility()
        self.request_utility = RequestsUtility(RAYDIUM["BASE_URL"])
        self.jupiter_requests = RequestsUtility(JUPITER_STATION["BASE_URL"])
        self.rug_check_utility = RugCheckUtility()
        self.excel_utility = ExcelUtility()
        self.helius_rate_limiter = rate_limiter
        self.settings = load_settings()
        self.volume_tracker = VolumeTracker()
        self.prepare_json_files()
        BOT_SETTINGS = get_bot_settings()
        jupiter_rl_settings = BOT_SETTINGS["RATE_LIMITS"]["jupiter"]
        self.jupiter_rate_limiter = RateLimiter(min_interval=jupiter_rl_settings["min_interval"],jitter_range=tuple(jupiter_rl_settings["jitter_range"]),max_requests_per_minute=jupiter_rl_settings["max_requests_per_minute"],name=jupiter_rl_settings["name"])
        self.api_key = credentials_utility.get_helius_api_key()
        self._private_key_solana = credentials_utility.get_solana_private_wallet_key()
        self.bird_api_key = credentials_utility.get_bird_eye_key()
        self.url = HELIUS_URL["BASE_URL"] + self.api_key["HELIUS_API_KEY"]
        self.client = Client(self.url, timeout=30)
        self.keypair = Keypair.from_base58_string(
            self._private_key_solana["SOLANA_PRIVATE_KEY"]
        )
        self.wallet_address = self.keypair.pubkey()
        logger.debug(
            f"Initialized TransactionHandler with wallet: {self.wallet_address}"
        )
        self.id = 1
        self._cached_sol_price = None
        self._last_sol_fetch = 0
        self._sol_cache_ttl = 5
        self.token_pools = {}
    
    def prepare_json_files(self):
        self.transaction_simulation_paylod = get_payload("Transaction_simulation")
        self.swap_payload = get_payload("Swap_token_payload")
        self.liquidity_payload = get_payload("Liquidity_payload")
        self.send_transaction_payload = get_payload("Send_transaction")
        self.asset_payload = get_payload("Asset_payload")
        self.largest_accounts_payload = get_payload("Largets_accounts")
        self.program_accounts = get_payload("Liquidity_payload")
        self.token_account_by_owner = get_payload("Token_account_by_owner")

    def get_account_balances(self) -> list:
        logger.debug(f"Fetching token balances for wallet: {self.wallet_address}")

        try:
            # Call your existing Helius wrapper
            accounts = self.get_token_accounts_by_owner(str(self.wallet_address))

            token_balances = []
            for acc in accounts:
                try:
                    mint = acc.get("mint")
                    amount = int(acc.get("amount", 0))
                    decimals = int(acc.get("decimals", 0))
                    balance = amount / (10 ** decimals) if decimals > 0 else amount

                    token_balances.append({
                        "token_mint": mint,
                        "balance": balance
                    })
                except Exception as inner_e:
                    logger.error(f"❌ Error processing token account {acc}: {inner_e}")

            # Add SOL balance
            try:
                sol_balance_response = self.client.get_balance(self.wallet_address)
                sol_balance = sol_balance_response.value / (10 ** 9)
                token_balances.insert(0, {"token_mint": "SOL", "balance": sol_balance})
            except Exception as sol_e:
                logger.warning(f"⚠️ Could not fetch SOL balance: {sol_e}")

            # Optionally filter out zero balances
            token_balances = [b for b in token_balances if b["balance"] > 0]

            logger.info(f"✅ Retrieved {len(token_balances)} token balances.")
            logger.debug(f"Token Balances: {token_balances}")

            return token_balances

        except Exception as e:
            logger.error(f"❌ Failed to fetch balances: {e}")
            return []

    def add_token_account(self, token_mint: str):
        """Ensure the wallet has an Associated Token Account (ATA) for a given token."""
        logger.debug(f"Checking token account for mint: {token_mint}")

        try:
            token_mint_pubkey = Pubkey.from_string(token_mint)
            associated_token_account = get_associated_token_address(
                owner=self.wallet_address, mint=token_mint_pubkey
            )

            # Check if the account already exists
            response = self.client.get_account_info(associated_token_account)
            logger.debug(f"Token Account Lookup Response: {response}")

            if response.value:
                logger.info(
                    f"✅ Token account already exists: {associated_token_account}"
                )
                return associated_token_account

            logger.info(f"Creating new token account for mint: {token_mint}")

            # ✅ Use the idempotent function to create an ATA if it doesn't exist
            transaction = Transaction()
            transaction.add(
                create_associated_token_account(
                    payer=self.wallet_address,
                    owner=self.wallet_address,
                    mint=token_mint_pubkey,
                )
            )

            # Fetch latest blockhash
            blockhash_resp = self.client.get_latest_blockhash()
            recent_blockhash = blockhash_resp.value.blockhash

            # Convert to MessageV0 and Sign
            message = MessageV0.try_compile(
                self.wallet_address, transaction.instructions, [], recent_blockhash
            )
            versioned_txn = VersionedTransaction(message, [self.keypair])

            # Send the transaction to create the token account
            send_response = self.client.send_transaction(versioned_txn)

            if send_response.value:
                logger.info(f"✅ Token account created: {associated_token_account}")
                logger.debug(f"Transaction Signature: {send_response.value}")
                return associated_token_account
            else:
                logger.warning(
                    f"⚠️ Token account creation might have failed: {send_response}"
                )
                return None

        except Exception as e:
            logger.error(f"❌ Failed to create token account: {e}")
            return None

    def buy(self, input_mint: str, output_mint: str, usd_amount: int, sim: bool = False) -> str:

        logger.info(f"🔄 Initiating buy for ${usd_amount} — Token: {output_mint}")
        try:
            token_amount = self.get_solana_token_worth_in_dollars(usd_amount)       
            quote = self.get_quote(input_mint, output_mint, token_amount,self.settings["SLPG"])
            if not quote:
                logger.warning("⚠️ No quote received, aborting buy.")
                return None

            logger.info(f"📦 Jupiter Quote: In = {quote['inAmount']}, Out = {quote['outAmount']}")
            quote_price = float(quote['outAmount']) / float(quote['inAmount'])
            logger.info(f"💡 Expected quote price: {quote_price:.10f}")
            
            #default data        
            now = datetime.now()
            date_str = now.strftime("%Y-%m-%d")
            time_str = now.strftime("%H:%M:%S")

            data = {
                "Timestamp": [f"{date_str} {time_str}"],
                "Quote_Price": [quote_price],
                "Token_sold": [input_mint],
                "Token_bought": [output_mint],
            }
            if sim:
                token_decimals = self.get_token_decimals(output_mint)
                token_received = float(quote["outAmount"]) / (10 ** token_decimals)
                if token_received == 0:
                    logger.warning(f"❌ Quote gives 0 tokens, skipping simulation for {output_mint}")
                    return None

                real_entry_price = usd_amount / token_received  

                data.update({
                    "type": ["SIMULATED_BUY"],
                    "Real_Entry_Price": [real_entry_price], 
                    "Token_Received": [token_received],
                    "WSOL_Spent": [0],
                    "Sold_At_Price": [0],
                    "SentToDiscord": [False],
                    "Signature": ["SIMULATED"],
                    "Entry_USD": [real_entry_price], 
                })
                self.excel_utility.save_to_csv(self.excel_utility.BOUGHT_TOKENS, f"simulated_tokens.csv", data)
                return "SIMULATED"


            # 🚀 Send transaction
            txn_64 = self.get_swap_transaction(quote)
            self.send_transaction_payload["params"][0] = txn_64
            self.send_transaction_payload["id"] = self.id
            self.id += 1
            self.helius_rate_limiter.wait()
            response = self.helius_requests.post(
                self.api_key["HELIUS_API_KEY"], payload=self.send_transaction_payload
            )
            logger.debug(f"Buy response: {response}")

            if "result" not in response:
                logger.warning(f"❌ Buy FAILED for {output_mint}: {response['error'].get('message')}")
                data.update({
                    "type": ["FAILED_BUY"],
                    "Error_Code": [response["error"]["code"]],
                    "Error_Message": [response["error"]["message"]],
                })
                self.excel_utility.save_to_csv(self.excel_utility.BOUGHT_TOKENS, f"failed_buys_{date_str}.csv", data)
                return None

            logger.info(f"✅ Buy SUCCESSFUL for {output_mint}")
            buy_signature = response.get("result", None)

            # Start tracking immediately with quote_price (approx)
            real_entry_price = quote_price
            data.update({
                "Real_Entry_Price": [real_entry_price],
                "Entry_USD": [real_entry_price],
                "Token_Received": [0],  # will update later
                "WSOL_Spent": [usd_amount / self.get_sol_price()],
                "type": ["BUY"],
                "Sold_At_Price": [0],
                "SentToDiscord": [False],
                "Signature": [buy_signature],
            })

            # Save instantly so tracker can pick it up
            self.excel_utility.save_to_csv(self.excel_utility.BOUGHT_TOKENS, f"bought_tokens_{date_str}.csv", data)
            self.excel_utility.save_to_csv(self.excel_utility.BOUGHT_TOKENS, "open_positions.csv", data)
            self.excel_utility.save_to_csv(self.excel_utility.BOUGHT_TOKENS, f"discord_{date_str}.csv", data)

            # Spawn async updater for true balance
            threading.Thread(
                target=self._update_entry_price_with_balance,
                args=(output_mint, usd_amount, date_str,  data),
                daemon=True
            ).start()

            return buy_signature

        except Exception as e:
            logger.error(f"❌ Exception during buy: {e}")
            return None

    def get_sol_price(self) -> float:
        now = time.time()
        if self._cached_sol_price and (now - self._last_sol_fetch < self._sol_cache_ttl):
            return self._cached_sol_price
        self.jupiter_rate_limiter.wait()
        response = self.jupiter_requests.get(
            "/price/v2?ids=So11111111111111111111111111111111111111112"
        )

        price = float(
            response["data"]["So11111111111111111111111111111111111111112"]["price"]
        )
        self._cached_sol_price = price
        self._last_sol_fetch = now
        return price

    def get_token_price_paid(self, token_mint: str) -> float:
        url = f"https://public-api.birdeye.so/defi/price?include_liquidity=true&address={token_mint}"

        headers = {
            "accept": "application/json",
            "x-chain": "solana",
            "X-API-KEY": self.bird_api_key["BIRD_EYE"],
        }
        response = requests.get(url, headers=headers)
        logger.debug(f"response: {response.json()}")
        return response.json()["data"]["value"]

    def get_solana_token_worth_in_dollars(self, usd_amount: int) -> float:
        sol_price = float(self.get_sol_price())
        sol_amount_needed = usd_amount / sol_price
        converted_tokens = int(sol_amount_needed * 10**9)
        return converted_tokens

    def get_token_worth_in_usd(self, token_mint: str, usd_amount: int):
        try:
            solana_tokens = self.get_solana_token_worth_in_dollars(usd_amount)
            token_quote = self.get_quote(
                "So11111111111111111111111111111111111111112", token_mint, solana_tokens
            )

            if "outAmount" not in token_quote:
                raise ValueError(f"❌ Failed to get token quote for {token_mint}")

            raw_token_amount = int(token_quote["outAmount"])

            # ✅ Step 1: Fetch the token's decimals
            token_decimals = self.get_token_decimals(token_mint)

            # ✅ Step 2: Convert the raw amount to real token amount
            token_amount = math.ceil(raw_token_amount / (10**token_decimals))

            return token_amount

        except Exception as e:
            logger.error(f"❌ Error getting token worth in USD: {e}")
            return None

    def get_quote(self, input_mint, output_mint, amount=1000, slippage=5):
        try:
            self.jupiter_rate_limiter.wait()
            quote_url = f"{JUPITER_STATION['QUOTE_ENDPOINT']}?inputMint={input_mint}&outputMint={output_mint}&amount={amount}&slippageBps={slippage}"
            quote_response = self.jupiter_requests.get(quote_url)

            if "error" in quote_response:
                logger.warning(f"⚠️ Quote attempt failed: {quote_response['error']}")
                return None

            logger.info(f"✅ Successfully retrieved quote.")
            logger.debug(f"Build swap transaction: {quote_response} Success.")
            return quote_response

        except Exception as e:
            logger.error(f"❌ Error retrieving quote: {e}")
            return None

    def get_swap_transaction(self, quote_response: dict):
        """Get a swap transaction from Jupiter API (Raydium/Orca)"""
        if not quote_response or "error" in quote_response:
            logger.error(f"❌ There is an error in quote: {quote_response}")
            return None

        try:
            self.jupiter_rate_limiter.wait()
            self.swap_payload["userPublicKey"] = str(self.keypair.pubkey())
            self.swap_payload["quoteResponse"] = quote_response

            swap_response = self.jupiter_requests.post(
                endpoint=JUPITER_STATION["SWAP_ENDPOINT"], payload=self.swap_payload
            )

            if "error" in swap_response:
                logger.warning(
                    f"⚠️ Error getting swap transaction: {swap_response['error']}"
                )
                return None

            swap_txn_base64 = swap_response["swapTransaction"]

            try:
                raw_bytes = base64.b64decode(swap_txn_base64)
                logger.info(f"✅ Swap transaction decoded successfully")
                raw_tx = VersionedTransaction.from_bytes(raw_bytes)
                signed_tx = VersionedTransaction(raw_tx.message, [self.keypair])
                logger.debug(
                    f"Signed transaction: {signed_tx}, Wallet address: {self.wallet_address}"
                )
                logger.info(
                    f"Signed transaction for Wallet address: {self.wallet_address}"
                )
                seralized_tx = bytes(signed_tx)
                signed_tx_base64 = base64.b64encode(seralized_tx).decode("utf-8")
                logger.debug(f"signed base64 transaction: {signed_tx_base64}")
                logger.info(f"signed base64 transaction")
                try:
                    tx_signature = str(signed_tx.signatures[0])
                    logger.info(f"Transaction signature: {tx_signature}")
                except Exception as e:
                    logger.error(f"❌ Transaction signature extraction failed: {e}")
                    tx_signature = None

            except Exception as e:
                logger.error(f"❌ Swap transaction is not valid Base64: {e}")
                return None

            return signed_tx_base64

        except Exception as e:
            logger.error(f"❌ Error building swap transaction: {e}")
            return None

    def simulate_transaction(self, transaction_base64):
        """Simulate a transaction using Helius RPC"""
        self.transaction_simulation_paylod["params"][0] = transaction_base64
        try:
            self.helius_rate_limiter.wait()
            response = self.helius_requests.post(
                endpoint=self.api_key["HELIUS_API_KEY"],
                payload=self.transaction_simulation_paylod,
            )
            logger.debug(f"Transaction Simulation Response: {response}")

            # Check if "error" exists in response
            if "error" in response:
                logger.warning(f"⚠️ Simulation failed: {response['error']}")
                logger.error(
                    f"simulation result: {response.get('result', 'No result')}"
                )
                return False

            # Check if "err" exists inside response["result"]["value"]
            err = response.get("result", {}).get("value", {}).get("err")
            if err is not None:
                logger.warning(f"⚠️ Simulation failed with error: {err}")
                return False  # Now correctly detects failure

            logger.info("✅ Transaction simulation successful!")
            return True

        except Exception as e:
            logger.error(f"❌ Error simulating transaction: {e}")
            return False

    def get_token_decimals(
        self,
        token_mint: str,
    ) -> int:
        try:
            token_mint = Pubkey.from_string(token_mint)
            response = self.client.get_token_supply(token_mint)

            if response.value.decimals:
                return math.ceil(response.value.decimals)
            else:
                logger.warning(
                    f"⚠️ Failed to retrieve decimals for {token_mint}, defaulting to 6."
                )
                return 6

        except Exception as e:
            logger.error(f"❌ Error getting token decimals: {e}")
            return 6

    def get_token_supply(self, mint_address: str) -> float:
        """Fetch total token supply from Solana RPC and scale it correctly."""
        try:
            token_mint = Pubkey.from_string(mint_address)
            response = self.client.get_token_supply(token_mint)
            if response.value:
                supply = float(response.value.ui_amount)
                return supply

        except Exception as e:
            print(f"❌ Error fetching token supply: {e}")

        return 0

    def get_token_marketcap(self, token_mint: str) -> float:
        try:
            price = self.get_token_price(token_mint)
            supply = self.get_token_supply(token_mint)
            market_cap = price* supply
            return market_cap
        except Exception as e:
            logger.error("Not Legit token")

    def sell(self, input_mint: str, output_mint: str) -> dict:
        logger.info(f"🔄 Initiating sell order: Selling {input_mint} for {output_mint}")

        try:
            # 1. Get token balance
            balances = self.get_account_balances()
            token_info = next((t for t in balances if t["token_mint"] == input_mint), None)
            if not token_info or token_info["balance"] <= 0:
                logger.warning(f"⚠️ No balance found for token: {input_mint}")
                return {"success": False, "executed_price": 0.0, "signature": ""}

            decimals = self.get_token_decimals(input_mint)
            raw_amount = int(token_info["balance"] * (10 ** decimals))

            # 2. Get quote
            quote = self.get_quote(input_mint, output_mint, raw_amount)
            if not quote:
                logger.warning("⚠️ Failed to get quote.")
                return {"success": False, "executed_price": 0.0, "signature": ""}

            # 3. Execute transaction
            txn_64 = self.get_swap_transaction(quote)
            self.send_transaction_payload["params"][0] = txn_64
            self.send_transaction_payload["id"] = self.id
            self.id += 1

            self.helius_rate_limiter.wait()
            response = self.helius_requests.post(
                self.api_key["HELIUS_API_KEY"], payload=self.send_transaction_payload
            )

            if "error" in response:
                logger.error(f"❌ Sell failed: {response['error']}")
                return {"success": False, "executed_price": 0.0, "signature": ""}

            signature = response["result"]
            logger.info(f"✅ Sell completed: Signature: {signature}")

            # 4. Calculate executed price from quote
            executed_price = float(quote["outAmount"]) / float(quote["inAmount"])

            return {
                "success": True,
                "executed_price": executed_price,
                "signature": signature,
            }

        except Exception as e:
            logger.error(f"❌ Exception during sell: {e}")
            return {"success": False, "executed_price": 0.0, "signature": ""}

    def is_token_scam(self, response_json, token_mint) -> bool:

        # Check if a swap route exists
        if "routePlan" not in response_json or not response_json["routePlan"]:
            logger.warning(f"🚨 No swap route for {token_mint}. Possible honeypot.")
            return True

        best_route = response_json["routePlan"][0]["swapInfo"]
        in_amount = float(best_route["inAmount"])
        out_amount = float(best_route["outAmount"])
        fee_amount = float(best_route["feeAmount"])

        fee_ratio = fee_amount / in_amount if in_amount > 0 else 0
        if fee_ratio > 0.05:
            logger.warning(
                f"⚠️ High tax detected ({fee_ratio * 100}%). Possible scam token."
            )
            return True

        logger.info("token scam test - tax check passed")

        if out_amount == 0:
            logger.warning(
                f"🚨 Token has zero output in swap! No liquidity detected for {token_mint}."
            )
            return True

        logger.info("token scam test - output check passed")

        if in_amount / out_amount > 10000:
            logger.warning(
                f"⚠️ Unreasonable token price ratio for {token_mint}. Possible rug."
            )
            return True

        logger.info("token scam test - price ratio check passed")
        logger.info(f"✅ Token {token_mint} passed Jupiter scam detection.")
        return False
    # paid version of liquidty and accurate
    def get_liqudity(self, new_token_mint: str) -> float:
        try:
            url = f"https://public-api.birdeye.so/defi/price?include_liquidity=true&address={new_token_mint}"

            headers = {
                "accept": "application/json",
                "x-chain": "solana",
                "X-API-KEY": self.bird_api_key["BIRD_EYE"],
            }
            response = requests.get(url, headers=headers)
            logger.info(response.json())
            logger.debug(f"response: {response.json()}")
            return response.json()["data"]["liquidity"]

        except Exception as e:
            logger.error(f"failed to retrive liquidity: {e}")

        return None
    # For Raydium-based logs
    def parse__raydium_liquidity_logs(self, logs: list[str], token_mint: str, transaction: dict) -> dict:
        result = {
            "itsa": None,
            "yta": None,
            "itsa_decimals": 6,
            "yta_decimals": 9,
            "source": None,
            "itsa_mint": None,
        }

        for log in logs:
            logger.debug(f"🔍 Log line: {log}")

            if result["itsa"] is None:
                itsa_match = re.search(r"itsa[:=]?\s*([0-9]+)", log)
                if itsa_match:
                    result["itsa"] = int(itsa_match.group(1))
                    result["source"] = "strategy"

            if result["yta"] is None:
                yta_match = re.search(r"yta[:=]?\s*([0-9]+)", log)
                if yta_match:
                    result["yta"] = int(yta_match.group(1))
                    result["source"] = "strategy"

            if "initialize" in log and ("init_pc_amount" in log or "init_coin_amount" in log):
                logger.debug(f"🔍 Raydium init log: {log}")
                pc_match = re.search(r"init_pc_amount:\s*([0-9]+)", log)
                coin_match = re.search(r"init_coin_amount:\s*([0-9]+)", log)

                if pc_match:
                    result["itsa"] = int(pc_match.group(1))
                    result["itsa_decimals"] = 9
                    result["source"] = "raydium"

                if coin_match:
                    result["yta"] = int(coin_match.group(1))
                    result["source"] = "raydium"

        # ✅ Fallback: Token balances
        if (
            (result["yta"] is None or result["yta"] == 0 or result["itsa"] is None or result["itsa"] == 0)
            and "postTokenBalances" in transaction.get("meta", {})
        ):
            for balance in transaction["meta"]["postTokenBalances"]:
                mint = balance.get("mint")
                amount = int(balance["uiTokenAmount"]["amount"])
                decimals = balance["uiTokenAmount"]["decimals"]

                if mint == token_mint and (result["yta"] is None or result["yta"] == 0):
                    result["yta"] = amount
                    result["yta_decimals"] = decimals
                elif mint != token_mint and (result["itsa"] is None or result["itsa"] == 0):
                    result["itsa"] = amount
                    result["itsa_decimals"] = decimals
                    result["itsa_mint"] = mint
                    result["source"] = "raydium"
        return self._calculate_liquidity(result, token_mint)
    # For Pump.fun-based logs
    def parse__pumpfun_liquidity_logs(self, logs: list[str], token_mint: str, transaction: dict) -> dict:
        result = {
            "itsa": None,
            "yta": None,
            "itsa_decimals": 9,  # Lamports (SOL)
            "yta_decimals": 9,
            "source": "pumpfun",
            "itsa_mint": None,
        }

        # 🔍 Try to extract from logs
        for log in logs:
            if "SwapEvent" in log or "Instruction: Buy" in log:
                result["source"] = "pumpfun"

                swap_match = re.search(r"amount_in\s*:\s*([0-9]+),\s*amount_out\s*:\s*([0-9]+)", log)
                if swap_match:
                    result["itsa"] = int(swap_match.group(1))
                    result["yta"] = int(swap_match.group(2))

            if result["itsa"] is None:
                match_in = re.search(r"amount_in\s*:\s*([0-9]+)", log)
                if match_in:
                    result["itsa"] = int(match_in.group(1))

            if result["yta"] is None:
                match_out = re.search(r"amount_out\s*:\s*([0-9]+)", log)
                if match_out:
                    result["yta"] = int(match_out.group(1))
            if result["itsa"] is not None and result["yta"] is not None:
                return self._calculate_liquidity(result, token_mint) 

        # ✅ Fallback outside the log loop
        if (
            (result["yta"] is None or result["yta"] == 0 or result["itsa"] is None or result["itsa"] == 0)
            and "postTokenBalances" in transaction.get("meta", {})
        ):
            for balance in transaction["meta"]["postTokenBalances"]:
                mint = balance.get("mint")
                amount = int(balance["uiTokenAmount"]["amount"])
                decimals = balance["uiTokenAmount"]["decimals"]

                if mint == token_mint and (result["yta"] is None or result["yta"] == 0):
                    result["yta"] = amount
                    result["yta_decimals"] = decimals
                elif mint != token_mint and (result["itsa"] is None or result["itsa"] == 0):
                    result["itsa"] = amount
                    result["itsa_decimals"] = decimals
                    result["itsa_mint"] = mint
        return self._calculate_liquidity(result, token_mint)
    # Shared liquidity post-processing
    def _calculate_liquidity(self, result: dict, token_mint: str) -> dict:
        if result["itsa"] is not None and result["yta"] is not None:
            try:
                result["yta_decimals"] = self.get_token_decimals(token_mint)
            except Exception as e:
                logger.warning(f"⚠️ Failed to fetch decimals for {token_mint}: {e}")
                result["yta_decimals"] = 9

            # Known base mints
            KNOWN_BASES = {
                "So11111111111111111111111111111111111111112": {"decimals": 9, "symbol": "SOL"},
                "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v": {"decimals": 6, "symbol": "USDC"},
                "Es9vMFrzaCERc1eZqDum62vD9BTezVXNid1QH2G2Vw5B": {"decimals": 6, "symbol": "USDT"},
            }

            itsa_mint = result.get("itsa_mint")
            itsa_decimals = result["itsa_decimals"]
            itsa_amount = result["itsa"] / (10 ** itsa_decimals)
            itsa_usd = 0

            if result["source"] in ["raydium", "pumpfun"]:
                if itsa_mint in KNOWN_BASES:
                    base_symbol = KNOWN_BASES[itsa_mint]["symbol"]
                    if base_symbol == "SOL":
                        try:
                            sol_price = self.get_sol_price()
                            itsa_usd = itsa_amount * sol_price
                        except Exception as e:
                            logger.warning(f"⚠️ Failed to fetch SOL price: {e}")
                            itsa_usd = 0
                    elif base_symbol in {"USDC", "USDT"}:
                        itsa_usd = itsa_amount  # Already USD
                else:
                    # fallback if base mint is unknown
                    logger.warning(f"⚠️ Unknown base mint for ITSA: {itsa_mint}, assuming USD = 0")
                    itsa_usd = 0

            yta_tokens = result["yta"] / (10 ** result["yta_decimals"])

            result["liquidity_usd"] = itsa_usd
            result["token_amount"] = yta_tokens
            result["launch_price_usd"] = round(itsa_usd / yta_tokens, 8) if yta_tokens > 0 else 0

            logger.debug(
                f"🧪 Liquidity calc for {token_mint} | itsa: {result['itsa']} "
                f"| yta: {result['yta']} | USD: {result.get('liquidity_usd', 0)}"
            )

        return result
    # helper free version of liquidity and estmiated
    def analyze_liquidty(self, logs: list[str], token_mint: str, dex: str, transaction):
        if dex.lower() == "raydium":
            liquidity_data = self.parse__raydium_liquidity_logs(logs, token_mint, transaction)
        elif dex.lower() == "pumpfun":
            liquidity_data = self.parse__pumpfun_liquidity_logs(logs, token_mint, transaction)
        else:
            logger.warning(f"Unknown DEX: {dex}")
            return 0

        if liquidity_data.get("liquidity_usd", 0) > 0:
            liquidity = liquidity_data["liquidity_usd"]
            launch_price = liquidity_data["launch_price_usd"]
            logger.info(
                f"💧 Liquidity detected for {token_mint} - ${liquidity:.2f}, Launch price: ${launch_price:.8f}"
            )
            return liquidity
        else:
            logger.info("ℹ️ No liquidity info found in logs.")
            return 0

    def get_token_prices(self, mints: list) -> dict:
        ids = ",".join(mints)
        self.jupiter_rate_limiter.wait()
        endpoint = f"{JUPITER_STATION['PRICE']}?ids={ids}&showExtraInfo=true"
        return self.jupiter_requests.get(endpoint)

    def get_token_price(self, mint: str) -> float:
        self.jupiter_rate_limiter.wait()
        endpoint = f"{JUPITER_STATION['PRICE']}?ids={mint}&showExtraInfo=true"
        data = self.jupiter_requests.get(endpoint)
        return float(data["data"][mint]["price"])
    
    def post_buy_delayed_check(self, token_mint, signature, liquidity, market_cap, attempt=1):
        logger.info(f"⏳ Running DELAYED post-buy check (attempt {attempt}) for {token_mint}...")

        results = {
            "LP_Check": "FAIL",
            "Holders_Check": "FAIL",
            "Volume_Check": "FAIL",
            "MarketCap_Check": "FAIL",
        }
        score = 0
        volume_stats = {"count": 0, "total_usd": 0.0}

        # LP lock ratio
        try:
            lp_status = self.rug_check_utility.is_liquidity_unlocked_test(token_mint)
            if lp_status == "safe":
                results["LP_Check"] = "PASS"
                score += 1
            elif lp_status == "risky":
                results["LP_Check"] = "RISKY"
                score += 0.5
        except Exception as e:
            logger.error(f"❌ LP check failed for {token_mint}: {e}")

        # Holder distribution
        try:
            if self.get_largest_accounts(token_mint):
                results["Holders_Check"] = "PASS"
                score += 1
        except Exception as e:
            logger.error(f"❌ Holder distribution check failed for {token_mint}: {e}")

        # Volume growth since launch
        try:
            launch_info = self.volume_tracker.token_launch_info.get(token_mint, {})
            launch_volume = launch_info.get("launch_volume", 0.0)
            launch_time = launch_info.get("launch_time")

            # Lifetime volume since first trade
            lifetime_trades = self.volume_tracker.volume_by_token.get(token_mint, [])
            current_volume = sum(usd for _, usd, _ in lifetime_trades)
            buy_usd = sum(usd for _, usd, ttype in lifetime_trades if ttype == "buy")
            sell_usd = sum(usd for _, usd, ttype in lifetime_trades if ttype == "sell")

            if current_volume > launch_volume and buy_usd > sell_usd:
                results["Volume_Check"] = "PASS"
                score += 1
            else:
                results["Volume_Check"] = (
                    f"FAIL (Launch ${launch_volume:.2f}, Now ${current_volume:.2f}, "
                    f"Buys ${buy_usd:.2f} vs Sells ${sell_usd:.2f})"
                )
        except Exception as e:
            logger.error(f"❌ Volume check failed for {token_mint}: {e}")


        # 4Market cap
        try:
            if market_cap and market_cap <= 1_000_000:
                results["MarketCap_Check"] = "PASS"
                score += 1
        except Exception as e:
            logger.error(f"❌ Market cap check failed for {token_mint}: {e}")

        logger.info(
            f"📊 Token {token_mint} scored {score}/4 | "
            f"LP={results['LP_Check']} | Holders={results['Holders_Check']} | "
            f"Volume={results['Volume_Check']} | MarketCap={results['MarketCap_Check']}"
        )

        # Save results to CSV
        try:
            self.excel_utility.save_to_csv(
                self.excel_utility.TOKENS_DIR,
                "post_buy_checks.csv",
                {
                    "Timestamp": [datetime.now().strftime("%Y-%m-%d %H:%M:%S")],
                    "Signature": [signature],
                    "Token Mint": [token_mint],
                    "Liquidity (Estimated)": [liquidity],
                    "Market Cap": [market_cap],
                    "Score": [score],
                    "LP_Check": [results["LP_Check"]],
                    "Holders_Check": [results["Holders_Check"]],
                    "Volume_Check": [results["Volume_Check"]],
                    "MarketCap_Check": [results["MarketCap_Check"]],

                    # 🔹 Volume essentials
                    "Launch Time": [launch_time],
                    "Launch Volume": [launch_volume],
                    "Current Time": [datetime.now().strftime("%Y-%m-%d %H:%M:%S")],
                    "Current Volume": [volume_stats.get("total_usd", 0.0)],
                },
            )
        except Exception as e:
            logger.error(f"❌ Failed to save post-buy checks for {token_mint}: {e}")

        return {"score": score, "results": results}

    def check_scam_functions_helius(self, token_mint: str) -> bool:
        # get token worth in usd so it wont fail the jupiter
        token_amount = self.get_solana_token_worth_in_dollars(15)
        qoute = self.get_quote(
            token_mint, "So11111111111111111111111111111111111111112", token_amount
        )
        if not qoute:
            return False
        if self.is_token_scam(qoute, token_mint):
            return False
        try:
            mint_info = self.get_mint_account_info(token_mint)

            #  Check Mint Authority (Prevents Rug Pulls)
            mint_authority = mint_info.get("mint_authority", None)
            if mint_authority:
                logger.warning(
                    f"🚨 Token {token_mint} still has mint authority ({mint_authority})! HIGH RISK."
                )
                return False

            ## Check Freeze Authority (Prevents Wallet Freezing)
            freeze_authority = mint_info.get("freeze_authority", None)
            if freeze_authority:
                logger.warning(
                    f"🚨 Token {token_mint} has freeze authority ({freeze_authority})! Devs can freeze funds. HIGH RISK."
                )
                return False


            if self.rug_check_utility.is_liquidity_unlocked(token_mint):
                    logger.warning(
                        f"🚨 Token {token_mint} is mutable, owned by dev, AND liquidity is NOT locked! HIGH RISK."
                    )
                    return False
            else:
                logger.info(
                        f"⚠️ Token {token_mint} is mutable & dev-owned, but liquidity is locked. Might be safe."
                    )

            logger.info(f"✅ Token {token_mint} Safe to proceed.")
            return True

        except Exception as e:
            logger.error(f"❌ Error checking scam tests: {e}")
            return False
    
    def get_largest_accounts(self, token_mint: str):
        """Fetch largest token holders and analyze risk."""
        logger.info(f"🔍 Checking token holders for {token_mint} using Helius...")

        # Prepare payload
        self.largest_accounts_payload["id"] = self.id
        self.id += 1
        self.largest_accounts_payload["params"][0] = token_mint

        try:
            self.helius_rate_limiter.wait()
            response_json = self.helius_requests.post(
                endpoint=self.api_key["HELIUS_API_KEY"],
                payload=self.largest_accounts_payload,
            )

            special_logger.debug(f"🔍 Raw Helius Largest Accounts Response: {response_json}")

            if "result" not in response_json:
                logger.warning(f"⚠️ Unexpected Helius response structure: {response_json}")
                return False

            holders = response_json["result"]["value"]
            total_supply = self.get_token_supply(token_mint)

            if total_supply == 0:
                logger.error("❌ Failed to fetch token supply. Skipping analysis.")
                return False

            # Sort holders by balance
            sorted_holders = sorted(holders, key=lambda x: float(x["uiAmount"]), reverse=True)
            
            #amount of holders
            if len(sorted_holders) < 20:
                return False

            top_holders = sorted_holders[:10]
            top_holder_percentages = [
                (float(holder["uiAmount"]) / total_supply) * 100 for holder in top_holders
            ]
            # 1. Top holder >30% → risky
            if top_holder_percentages[0] > 30:
                return False

            # 2. Top 5 holders >70% combined → risky
            if sum(top_holder_percentages[:5]) > 70:
                return False

            # 3. Uniform bot-like distribution (>5% each, nearly equal)
            if len(top_holder_percentages) > 1:
                min_pct = min(top_holder_percentages[1:])
                max_pct = max(top_holder_percentages[1:])
                if abs(max_pct - min_pct) < 0.01 and max_pct > 5:
                    return False

            # 4. If dev not top holder (<2%) but someone else has >6% → risky
            if top_holder_percentages[0] < 2 and max(top_holder_percentages[1:]) > 6:
                return False

            logger.info("✅ Token Holder Analysis Complete.")
            return True

        except Exception as e:
            logger.error(f"❌ Error fetching largest accounts from Helius: {e}")
            return False

    def get_burned_accounts(self, token_mint: str):
        """Fetch largest token holders and analyze risk."""
        logger.info(f"🔍 Checking token holders for {token_mint} using Helius...")

        # Prepare payload
        self.largest_accounts_payload["id"] = self.id
        self.id += 1
        self.largest_accounts_payload["params"][0] = token_mint

        try:
            self.helius_rate_limiter.wait()
            response_json = self.helius_requests.post(
                endpoint=self.api_key["HELIUS_API_KEY"],
                payload=self.largest_accounts_payload,
            )

            special_logger.debug(f"🔍 Raw Helius Largest Accounts Response: {response_json}")

            if "result" not in response_json:
                logger.warning(f"⚠️ Unexpected Helius response structure: {response_json}")
                return False

            holders = response_json["result"]["value"]
            burned_accounts = []

            for h in holders:
                addr = h["address"]
                bal = float(h["uiAmount"])

                # Heuristics: detect burns
                if (
                    "dead" in addr.lower() or
                    "burn" in addr.lower() or
                    addr.startswith("111111")
                ):
                    burned_accounts.append({
                        "address": addr,
                        "balance": bal
                    })
            return burned_accounts
        except Exception as e:
            logger.error(f"❌ Error fetching burned accounts from Helius: {e}")
            return False

    def get_mint_account_info(self, mint_address: str) -> dict:
        resp = self.client.get_account_info(Pubkey.from_string(mint_address))

        if not resp.value or not resp.value.data:
            return {}

        raw_data = resp.value.data
        if isinstance(raw_data, bytes):  
            decoded = raw_data
        elif isinstance(raw_data, list):  
            decoded = bytes(raw_data)
        elif isinstance(raw_data, str):  
            decoded = base64.b64decode(raw_data)
        else:
            raise ValueError(f"Unexpected account data format: {type(raw_data)}")

        # --- Mint authority ---
        mint_auth_option = struct.unpack_from("<I", decoded, 0)[0]
        mint_authority = None
        if mint_auth_option == 1:
            mint_authority = str(Pubkey(decoded[4:36]))

        # --- Supply ---
        supply = struct.unpack_from("<Q", decoded, 36)[0]

        # --- Decimals & init flag ---
        decimals = decoded[44]
        is_initialized = decoded[45] == 1

        # --- Freeze authority ---
        freeze_auth_option = struct.unpack_from("<I", decoded, 46)[0]
        freeze_authority = None
        if freeze_auth_option == 1:
            freeze_authority = str(Pubkey(decoded[50:82]))

        return {
            "mint_authority": mint_authority,
            "freeze_authority": freeze_authority,
            "supply": supply,
            "decimals": decimals,
            "initialized": is_initialized,
        }

    def get_token_meta_data(self, token_mint: str):
        special_logger.info(f"🔍 Fetching metadata for {token_mint} using Helius...")
        self.asset_payload["id"] = self.id
        self.id += 1
        try:
            self.asset_payload["params"]["id"] = token_mint
            self.helius_rate_limiter.wait()
            response_json = self.helius_requests.post(
                endpoint=self.api_key["HELIUS_API_KEY"],
                payload=self.asset_payload,
            )

            if "result" not in response_json:
                logger.warning(f"⚠️ Unexpected Helius response structure: {response_json}")
                return False

            result = response_json["result"]
            content = result.get("content", {})

            token_name = content.get("metadata", {}).get("name")
            token_image = content.get("links", {}).get("image")
            token_address = result.get("id")

            return {
                "name": token_name,
                "image": token_image,
                "token_address": token_address,
            }
        except Exception as e:
            logger.error(f"❌ Error fetching token data: {e}")
            return False
    
    def extract_swap_volume(self, tx_data: dict, token_mint: str) -> dict:
        try:
            meta = tx_data.get("meta", {})

            pre_balances = meta.get("preTokenBalances", [])
            post_balances = meta.get("postTokenBalances", [])

            logger.debug(f"🔍 Pre balances: {pre_balances}")
            logger.debug(f"🔍 Post balances: {post_balances}")

            buy_usd, sell_usd = 0.0, 0.0

            for pre in pre_balances:
                mint = pre.get("mint")
                post = next(
                    (b for b in post_balances if b["accountIndex"] == pre["accountIndex"]),
                    None
                )

                logger.debug(
                    f"⚖️ Checking mint {mint} | pre={pre.get('uiTokenAmount')} | post={post.get('uiTokenAmount') if post else None}"
                )

                if not post:
                    continue

                before_amt = float(pre["uiTokenAmount"]["uiAmount"] or 0)
                after_amt = float(post["uiTokenAmount"]["uiAmount"] or 0)
                delta = after_amt - before_amt

                logger.debug(f"📊 Mint {mint}: before={before_amt}, after={after_amt}, delta={delta}")

                if abs(delta) < 1e-12:
                    continue

                # Convert to USD
                usd_value = 0.0
                if mint == "So11111111111111111111111111111111111111112":  # WSOL
                    try:
                        sol_price = self.get_sol_price()
                    except Exception as e:
                        logger.warning(f"⚠️ Failed to fetch SOL price: {e}")
                        sol_price = 0.0
                    usd_value = abs(delta) * sol_price
                elif mint in {
                    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",  # USDC
                    "Es9vMFrzaCERc1eZqDum62vD9BTezVXNid1QH2G2Vw5B",  # USDT
                }:
                    usd_value = abs(delta)  # already USD
                else:
                    logger.debug(f"❓ Unknown base mint {mint}, skipping pricing")
                    usd_value = 0.0

                if delta < 0:
                    buy_usd += usd_value
                    logger.debug(f"🟢 BUY detected: {usd_value} USD")
                else:
                    sell_usd += usd_value
                    logger.debug(f"🔴 SELL detected: {usd_value} USD")

            result = {
                "token_mint": token_mint,
                "buy_usd": round(buy_usd, 2),
                "sell_usd": round(sell_usd, 2),
                "total_usd": round(buy_usd + sell_usd, 2),
            }

            logger.info(f"📦 Swap volume result: {result}")
            return result

        except Exception as e:
            logger.error(f"❌ Failed to extract swap volume: {e}", exc_info=True)
            return {
                "token_mint": token_mint,
                "buy_usd": 0.0,
                "sell_usd": 0.0,
                "total_usd": 0.0,
            }

    def get_token_accounts_by_owner(self, pool_address: str):
        logger.info(f"🔍 Checking token pool reserves using Helius...")

        # Prepare payload
        self.token_account_by_owner["id"] = self.id
        self.id += 1
        self.token_account_by_owner["params"][0] = pool_address
        self.token_account_by_owner["params"][1]["programId"] = str(SPL_TOKEN_PROGRAM_ID)

        try:
            self.helius_rate_limiter.wait()
            response_json = self.helius_requests.post(
                endpoint=self.api_key["HELIUS_API_KEY"],
                payload=self.token_account_by_owner,
            )

            special_logger.debug(f"🔍 Raw Helius token accounts by owner Response: {response_json}")

            if "result" not in response_json:
                logger.warning(f"⚠️ Unexpected Helius response structure: {response_json}")
                return False

            accounts = response_json.get("result", {}).get("value", {}).get("accounts", [])
            reserves = []

            for acc in accounts:
                parsed_info = acc["account"]["data"]["parsed"]["info"]
                ta = parsed_info["tokenAmount"]
                reserves.append({
                    "mint": parsed_info["mint"],
                    "amount": int(ta["amount"]),
                    "decimals": int(ta["decimals"]),
                })

            return reserves
        except Exception as e:
                    logger.error(f"❌ Failed to fetch pool reserves: {e}", exc_info=True)
                    return []
    
    def calculate_on_chain_price(self,reserve_token: int,token_decimals: int,reserve_base: int,base_decimals: int,base_symbol: str,sol_price: float) -> float:
            """Compute token price in USD from pool reserves."""
            token_amount = reserve_token / (10 ** token_decimals)
            base_amount = reserve_base / (10 ** base_decimals)

            if token_amount == 0:
                return 0.0

            price_in_base = base_amount / token_amount

            if base_symbol == "SOL":
                return price_in_base * sol_price
            elif base_symbol in {"USDC", "USDT"}:
                return price_in_base
            else:
                return 0.0

    def get_token_price_onchain(self, token_mint: str, pool_address: str) -> float:
        """Get USD price for a token using pool reserves and base token info."""
        try:
            reserves = self.get_token_accounts_by_owner(pool_address)
            if len(reserves) < 2:
                logger.warning(f"⚠️ Pool {pool_address} has insufficient reserves")
                return 0.0

            # Split reserves into token vs base
            token_reserve = next(r for r in reserves if r["mint"] == token_mint)
            base_reserve = next(r for r in reserves if r["mint"] != token_mint)

            # Detect base symbol
            base_info = KNOWN_BASES.get(base_reserve["mint"])
            if not base_info:
                logger.warning(f"⚠️ Unknown base mint {base_reserve['mint']} in pool {pool_address}")
                return 0.0

            return self.calculate_on_chain_price(
                reserve_token=token_reserve["amount"],
                token_decimals=token_reserve["decimals"],
                reserve_base=base_reserve["amount"],
                base_decimals=base_reserve["decimals"],
                base_symbol=base_info["symbol"],
                sol_price=self.get_sol_price()
            )

        except Exception as e:
            logger.error(f"❌ Failed to fetch on-chain price for {token_mint}: {e}", exc_info=True)
            return 0.0

    def get_current_price_on_chain(self, token_mint: str) -> float:
        """Lookup stored pool for a token and return its USD price."""
        pool_entry = self.token_pools.get(token_mint)
        if not pool_entry:
            logger.warning(f"⚠️ No pool stored for {token_mint}, cannot fetch price.")
            return 0.0

        pool_address = pool_entry["pool"] if isinstance(pool_entry, dict) else pool_entry
        return self.get_token_price_onchain(token_mint, pool_address)
    
    def store_pool_mapping(self, token_mint: str, transaction: dict):
        try:
            logs = transaction.get("meta", {}).get("logMessages", [])
            post_balances = transaction.get("meta", {}).get("postTokenBalances", [])
            keys = transaction.get("transaction", {}).get("message", {}).get("accountKeys", [])

            pool_address, dex = None, None


            pool_address = self.detect_pool_pda(post_balances, token_mint)

            # decide dex type by program ID present
            if PUMPFUN_PROGRAM_ID in keys:
                dex = "pumpfun"
            elif RAYDIUM_PROGRAM_ID in keys:
                dex = "raydium"

            if pool_address:
                prev_entry = self.token_pools.get(token_mint)
                self.token_pools[token_mint] = {"pool": pool_address, "dex": dex}

                if prev_entry and prev_entry["pool"] != pool_address:
                    logger.info(
                        f"🔄 Token {token_mint} migrated pool "
                        f"{prev_entry['pool']} ({prev_entry['dex']}) → {pool_address} ({dex})"
                    )
                    migration_flag = "MIGRATED"
                else:
                    logger.info(f"💾 Stored pool {pool_address} ({dex}) for {token_mint}")
                    migration_flag = "NEW"

                # Save/update CSV with migration info
                self.excel_utility.save_to_csv(
                    self.excel_utility.TOKENS_DIR,
                    "Pair_keys.csv",
                    {
                        "Token Mint": [token_mint],
                        "pair_key": [pool_address],
                        "pool_dex": [dex],
                        "status": [migration_flag],
                    },
                )
            else:
                logger.warning(f"⚠️ No pool detected for {token_mint}")

        except Exception as e:
            logger.warning(f"⚠️ Failed to store pool for {token_mint}: {e}")

    def detect_pool_pda(self, post_token_balances: list[dict], token_mint: str) -> str | None:

        WSOL = "So11111111111111111111111111111111111111112"
        candidates = []

        for bal in post_token_balances:
            mint = bal.get("mint")
            owner = bal.get("owner")
            ui_amount = bal.get("uiTokenAmount", {}).get("uiAmount", 0)

            if not mint or not owner:
                continue

            candidates.append((owner, mint, ui_amount))

        # Group balances by owner
        owner_balances = {}
        for owner, mint, amount in candidates:
            if owner not in owner_balances:
                owner_balances[owner] = {}
            owner_balances[owner][mint] = amount

        # Find owners that have both WSOL + token
        valid_pools = []
        for owner, balances in owner_balances.items():
            if WSOL in balances and token_mint in balances:
                total_liquidity = balances[WSOL] + balances[token_mint]
                valid_pools.append((owner, total_liquidity))

        if not valid_pools:
            return None

        # ✅ Return the owner with the largest combined WSOL+token balance
        logger.debug(f"token owners are {valid_pools}")
        best_owner, _ = max(valid_pools, key=lambda x: x[1])
        return best_owner

    def _update_entry_price_with_balance(self, output_mint: str, usd_amount: float, date_str: str, data: dict):
        MAX_RETRIES = 15
        WAIT_TIME = 2
        token_received = 0

        for attempt in range(MAX_RETRIES):
            time.sleep(WAIT_TIME)
            balances = self.get_account_balances()
            token_info = next((b for b in balances if b['token_mint'] == output_mint), None)
            if token_info and token_info['balance'] > 0:
                token_received = token_info['balance']
                logger.info(f"✅ Token received after buy: {token_received}")
                break
            logger.warning(f"🔁 Attempt {attempt + 1}: Token not received yet...")

        if token_received > 0:
            real_entry_price = usd_amount / token_received
        else:
            return
        # Update files with true entry price
        data.update({
            "Real_Entry_Price": [real_entry_price],
            "Entry_USD": [real_entry_price],
            "Token_Received": [token_received],
        })

        self.excel_utility.save_to_csv(self.excel_utility.BOUGHT_TOKENS, f"bought_tokens_{date_str}.csv", data)
        self.excel_utility.save_to_csv(self.excel_utility.BOUGHT_TOKENS, "open_positions.csv", data)
        self.excel_utility.save_to_csv(self.excel_utility.BOUGHT_TOKENS, f"discord_{date_str}.csv", data)

        logger.info(f"📊 Entry price updated for {output_mint}: {real_entry_price:.8f} USD")
