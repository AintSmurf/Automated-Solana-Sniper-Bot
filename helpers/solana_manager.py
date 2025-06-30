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
from helpers.rate_limiter_jupiter import RateLimiter
import time




# Set up logger
logger = LoggingHandler.get_logger()
special_logger = LoggingHandler.get_special_debug_logger()
JUPITER_LIMITER = RateLimiter()


class SolanaHandler:
    def __init__(self):
        self.helius_requests = RequestsUtility(HELIUS_URL["BASE_URL"])
        credentials_utility = CredentialsUtility()
        self.request_utility = RequestsUtility(RAYDIUM["BASE_URL"])
        self.jupiter_requests = RequestsUtility(JUPITER_STATION["BASE_URL"])
        self.rug_check_utility = RugCheckUtility()
        self.excel_utility = ExcelUtility()
        self.transaction_simulation_paylod = get_payload("Transaction_simulation")
        self.swap_payload = get_payload("Swap_token_payload")
        self.liquidity_payload = get_payload("Liquidity_payload")
        self.send_transaction_payload = get_payload("Send_transaction")
        self.asset_payload = get_payload("Asset_payload")
        self.largest_accounts_payload = get_payload("Largets_accounts")
        self.program_accounts = get_payload("Liquidity_payload")
        self.api_key = credentials_utility.get_helius_api_key()
        self._private_key_solana = credentials_utility.get_solana_private_wallet_key()
        self.bird_api_key = credentials_utility.get_bird_eye_key()
        self.url = HELIUS_URL["BASE_URL"] + self.api_key["API_KEY"]
        self.client = Client(self.url, timeout=30)
        self.keypair = Keypair.from_base58_string(
            self._private_key_solana["SOLANA_PRIVATE_KEY"]
        )
        self.wallet_address = self.keypair.pubkey()
        logger.debug(
            f"Initialized TransactionHandler with wallet: {self.wallet_address}"
        )
        self.id = 1

    def get_account_balances(self) -> list:
        logger.debug(f"Fetching token balances for wallet: {self.wallet_address}")

        try:
            sol_balance_response = self.client.get_balance(self.wallet_address)
            sol_balance = sol_balance_response.value / (10**9)
            response = self.client.get_token_accounts_by_owner(
                self.wallet_address,
                TokenAccountOpts(
                    program_id=Pubkey.from_string(
                        "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
                    ),
                    encoding="base64",
                ),
            )
            logger.debug(f"Solana RPC Response: {response}")

            if not response.value:
                logger.warning("⚠️ No token accounts found.")
                return [{"token_mint": "SOL", "balance": sol_balance}]

            token_balances = []
            for token in response.value:
                try:
                    account_data = bytes(token.account.data)
                    mint_pubkey = Pubkey(account_data[:32])
                    raw_amount = struct.unpack("<Q", account_data[64:72])[0]
                    token_info = self.client.get_token_supply(mint_pubkey)
                    decimals = token_info.value.decimals
                    balance = raw_amount / (10**decimals)
                    token_balances.append(
                        {"token_mint": str(mint_pubkey), "balance": balance}
                    )
                except Exception as inner_e:
                    logger.error(f"❌ Error processing token {token.pubkey}: {inner_e}")
            token_balances.insert(0, {"token_mint": "SOL", "balance": sol_balance})
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

    def buy(self, input_mint: str, output_mint: str, usd_amount: int) -> str:
        logger.info(
            f"🔄 Initiating buy order for {usd_amount}$ worth\ntoken_bought:{output_mint}\ntoken_sold:{input_mint}"
        )
        try:
            token_amount = self.get_solana_token_worth_in_dollars(usd_amount)
            quote = self.get_quote(input_mint, output_mint, token_amount)
            price_per_token = usd_amount / float(quote["outAmount"])
            print("token prince: ", price_per_token)
            txn_64 = self.get_swap_transaction(quote)
            self.send_transaction_payload["params"][0] = txn_64
            self.send_transaction_payload["id"] = self.id
            self.id += 1
            response = self.helius_requests.post(
                self.api_key["API_KEY"], payload=self.send_transaction_payload
            )
            logger.debug(f" buy response {response}")
            # adjust key if needed
            now = datetime.now()
            date_str = now.strftime("%Y-%m-%d")
            time_str = now.strftime("%H:%M:%S")
            filename = f"bought_tokens_{date_str}.csv"
            token_price = self.get_token_price(output_mint)
            # save all tokens
            self.excel_utility.save_to_csv(
                self.excel_utility.BOUGHT_TOKENS,
                filename,
                {
                    "Timestamp": [f"{date_str} {time_str}"],
                    "Token_price": [token_price],
                    "Token_sold": [input_mint],
                    "Token boguht": [output_mint],
                    "amount": [token_amount],
                    "USD": [usd_amount],
                    "type": "BUY",
                    "Sold_At_Price": "",
                },
            )
            return response["result"]
        except Exception as e:
            logger.error(f"❌ Failed to place buy order: {e}")

    def get_sol_price(self) -> float:
        response = self.jupiter_requests.get(
            "/price/v2?ids=So11111111111111111111111111111111111111112"
        )
        return float(
            response["data"]["So11111111111111111111111111111111111111112"]["price"]
        )

    def get_token_price(self, token_mint: str) -> float:
        url = f"https://public-api.birdeye.so/defi/price?include_liquidity=true&address={token_mint}"

        headers = {
            "accept": "application/json",
            "x-chain": "solana",
            "X-API-KEY": "01876fc6d5944c7e80b57b0b929c1a4c",
        }
        response = requests.get(url, headers=headers)
        logger.info(f"response: {response.json()}")
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
            JUPITER_LIMITER.wait()
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
            JUPITER_LIMITER.wait()
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
            response = self.helius_requests.post(
                endpoint=self.api_key["API_KEY"],
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

    def get_raydium_marketcap(self, token_mint: str) -> float:
        try:

            self.liquidity_payload["mint1"] = token_mint
            response_data = self.request_utility.get(
                endpoint=RAYDIUM["LIQUIDITY"], payload=self.liquidity_payload
            )

            if not response_data.get("data") or not response_data["data"].get("data"):
                logger.error(f"No liquidity pool found for token: {token_mint}")
                return 0

            pool_data = response_data["data"]["data"][0]

            token_price = float(pool_data.get("price", 0))
            sol_price = self.get_sol_price()

            if token_price > 10 and sol_price:
                token_price *= sol_price

            total_supply = self.get_token_supply(token_mint)
            decimals = self.get_token_decimals(token_mint)
            total_supply /= 10**decimals

            if token_price <= 0 or total_supply <= 0:
                logger.warning(
                    f"Invalid price ({token_price}) or supply ({total_supply}) for {token_mint}"
                )
                return 0

            market_cap = total_supply * token_price
            logger.info(f"✅ Market Cap for {token_mint}: {market_cap}")

            return market_cap

        except Exception as e:
            logger.error(f"❌ Error fetching market cap: {e}")
            return 0

    def sell(self, input_mint: str, output_mint: str, usd_amount: int = None) -> None:
        logger.info(
            f"🔄 Initiating sell order\nToken Sold: {input_mint}\nToken Received: {output_mint}"
        )
        try:
            token_balances = self.get_account_balances()
            token_info = next(
                (t for t in token_balances if t["token_mint"] == input_mint), None
            )

            if not token_info:
                logger.warning(f"⚠️ No balance found for token: {input_mint}")
                return

            token_balance = token_info["balance"]
            decimals = self.get_token_decimals(input_mint)
            raw_amount = int(float(token_balance) * (10**decimals))

            if token_balance <= 0:
                logger.warning(f"⚠️ No tokens to sell for {input_mint}")
                return
            quote = self.get_quote(input_mint, output_mint, raw_amount)
            txn_64 = self.get_swap_transaction(quote)
            self.send_transaction_payload["params"][0] = txn_64
            self.send_transaction_payload["id"] = self.id
            self.id += 1
            response = self.helius_requests.post(
                self.api_key["API_KEY"], payload=self.send_transaction_payload
            )
            logger.info(f"✅ Sell order completed: {response}")
        except Exception as e:
            logger.error(f"❌ Failed to place sell order: {e}")

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
    def parse__raydium_liquidity_logs(self, logs: list[str], token_mint: str) -> dict:
        result = {
            "itsa": None,
            "yta": None,
            "itsa_decimals": 6,  # Default USDC
            "yta_decimals": 9,   # Default memecoin
            "source": None,
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

            if "initialize2: InitializeInstruction2" in log:
                logger.debug(f"🔍 Raw initialize2 log: {log}")
                pc_match = re.search(r"init_pc_amount:\s*([0-9]+)", log)
                coin_match = re.search(r"init_coin_amount:\s*([0-9]+)", log)

                if pc_match:
                    result["itsa"] = int(pc_match.group(1))
                    result["itsa_decimals"] = 9
                    result["source"] = "raydium"
                if coin_match:
                    result["yta"] = int(coin_match.group(1))
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

            itsa_usd = result["itsa"] / (10 ** result["itsa_decimals"])
            SOL_MINTS = {
                "So11111111111111111111111111111111111111112", 
            }
            is_sol = result.get("itsa_mint") in SOL_MINTS or result["itsa_decimals"] == 9

            if result["source"] in ["raydium", "pumpfun"] and is_sol:
                try:
                    sol_price = self.get_sol_price()
                    itsa_usd *= sol_price
                except Exception as e:
                    logger.warning(f"⚠️ Failed to fetch SOL price: {e}")
                    itsa_usd = 0


            yta_tokens = result["yta"] / (10 ** result["yta_decimals"])

            result["liquidity_usd"] = itsa_usd
            result["token_amount"] = yta_tokens
            result["launch_price_usd"] = (
                round(itsa_usd / yta_tokens, 8) if yta_tokens > 0 else 0
            )
            logger.debug(f"🧪 Liquidity calc for {token_mint} | itsa: {result['itsa']} | yta: {result['yta']} | USD: {result.get('liquidity_usd', 0)}")
        return result
    # helper free version of liquidity and estmiated
    def analyze_liquidty(self, logs: list[str], token_mint: str, dex: str, transaction):
        if dex.lower() == "raydium":
            liquidity_data = self.parse__raydium_liquidity_logs(logs, token_mint)
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
        JUPITER_LIMITER.wait()
        endpoint = f"{JUPITER_STATION['PRICE']}?ids={ids}&showExtraInfo=true"
        return self.jupiter_requests.get(endpoint)

    def get_token_price(self, mint: str) -> float:
        JUPITER_LIMITER.wait()
        endpoint = f"{JUPITER_STATION['PRICE']}?ids={mint}&showExtraInfo=true"
        data = self.jupiter_requests.get(endpoint)
        return data["data"][mint]["price"]
    
    def post_buy_safety_check(self, token_mint, token_owner, signature, liquidity, market_cap):
        logger.info(f"🔍 Running post-buy safety check for {token_mint}...")
        final_reason = "unknown"

        for attempt in range(4):  # 1 initial + 3 retries
            if attempt > 0:
                logger.info(f"⏳ Rechecking {token_mint} — Attempt {attempt + 1}/4")
                time.sleep(10)

            try:
                score = 0  # 🧮 reset per attempt

                # 1️⃣ LP Unlock Status
                lp_status = self.rug_check_utility.is_liquidity_unlocked_test(token_mint)
                if lp_status == "safe":
                    score += 1
                elif lp_status == "risky":
                    score += 0.5
                elif lp_status == "unknown":
                    score += 0.25
                special_logger.debug(f"score after liquidty {score} for {token_mint}")
                # 2️⃣ Scam Code Check
                if not self.check_scam_functions_helius(token_mint):
                    final_reason = "scam_functions_detected"
                    logger.warning(f"❌ {token_mint} failed: {final_reason}")
                    continue
                score += 1

                # 3️⃣ Holder Distribution
                if not self.get_largest_accounts(token_mint):
                    final_reason = "bad_holder_distribution"
                    logger.warning(f"❌ {token_mint} failed: {final_reason}")
                    continue
                score += 1

                logger.info(f"📊 Final score for {token_mint}: {score}/3")

                if score >= 2.5:
                    logger.info(f"✅ {token_mint} PASSED post-buy safety check. Logging as safe.")
                    now = datetime.now()
                    date_str = now.strftime("%Y-%m-%d")
                    time_str = now.strftime("%H:%M:%S")
                    self.excel_utility.save_to_csv(
                        self.excel_utility.TOKENS_DIR,
                        f"safe_tokens_{date_str}.csv",
                        {
                            "Timestamp": [f"{date_str} {time_str}"],
                            "Signature": [signature],
                            "Token Mint": [token_mint],
                            "Token Owner": [token_owner],
                            "Liquidity (Estimated)": [liquidity],
                            "Market Cap": [market_cap],
                            "Score": [score],
                            "SentToDiscord": False,
                        },
                    )
                    return  # ✅ Exit on success

                final_reason = f"low_score_{score}"

            except Exception as e:
                final_reason = f"exception_attempt_{attempt + 1}"
                logger.error(f"⚠️ Error during check (attempt {attempt + 1}): {e}")

        # ❌ All attempts failed or score too low
        logger.warning(f"❌ {token_mint} FAILED post-buy safety check after 4 attempts.")
        self.log_failed_token(token_mint, token_owner, signature, liquidity, market_cap, final_reason)

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

        special_logger.info(f"🔍 Checking scams for {token_mint} using Helius...")
        self.asset_payload["id"] = self.id
        self.id += 1
        self.asset_payload["params"]["id"] = token_mint

        try:
            response_json = self.helius_requests.post(
                endpoint=self.api_key["API_KEY"],
                payload=self.asset_payload,
            )
            special_logger.debug(f"🔍 Raw Helius Response for {response_json}")
            if "result" not in response_json:
                logger.warning(
                    f"⚠️ Unexpected Helius response structure: {response_json}"
                )
                return False

            asset_data = response_json["result"]
            token_info = asset_data.get("token_info", {})

            #  Check Mint Authority (Prevents Rug Pulls)
            mint_authority = token_info.get("mint_authority", None)
            if mint_authority not in [None, ""]:
                logger.warning(
                    f"🚨 Token {token_mint} still has mint authority ({mint_authority})! HIGH RISK."
                )
                return False

            ## Check Freeze Authority (Prevents Wallet Freezing)
            freeze_authority = token_info.get("freeze_authority", None)
            if freeze_authority:
                logger.warning(
                    f"🚨 Token {token_mint} has freeze authority ({freeze_authority})! Devs can freeze funds. HIGH RISK."
                )
                return False

            ##  Check Burn Status
            if asset_data.get("burnt", False):
                logger.warning(
                    f"🔥 Token {token_mint} is burnt and cannot be used anymore."
                )
                return False

            ##  Check Mutability & Ownership
            if asset_data.get("mutable", True) and asset_data.get("authorities", []):
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
            logger.error(f"❌ Error fetching contract code from Helius: {e}")
            return False
    
    def get_largest_accounts(self, token_mint: str):
        """Fetch largest token holders and analyze risk."""
        logger.info(f"🔍 Checking token holders for {token_mint} using Helius...")

        # Prepare payload
        self.largest_accounts_payload["id"] = self.id
        self.id += 1
        self.largest_accounts_payload["params"][0] = token_mint

        try:
            response_json = self.helius_requests.post(
                endpoint=self.api_key["API_KEY"],
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

            top_holders = sorted_holders[:10]
            top_holder_percentages = [
                (float(holder["uiAmount"]) / total_supply) * 100 for holder in top_holders
            ]

            if not top_holder_percentages:
                logger.warning("❌ No holder data found.")
                return False

            # # 🚩 Flag: Top holder has too much (centralized risk)
            # if top_holder_percentages[0] > 50:
            #     special_logger.debug("⚠️ Top holder owns over 20% — High centralization.")
            #     return False
            special_logger.info(
                f"ℹ️ Top holder owns {top_holder_percentages[0]:.2f}% — Ignored due to hit-and-run strategy."
            )

            # 🚩 Flag: Uniform bot-like holders with high % between them
            if len(top_holder_percentages) > 1:
                min_pct = min(top_holder_percentages[1:])
                max_pct = max(top_holder_percentages[1:])
                if abs(max_pct - min_pct) < 0.01 and max_pct > 5:
                    special_logger.debug("⚠️ Uniform bot-like holders >5% — Risky.")
                    return False

                # 🚩 Flag: Dev not top holder + others dominate
                if top_holder_percentages[0] < 2 and max_pct > 6:
                    special_logger.debug("⚠️ Top holder too small, other wallets dominate — Risk.")
                    return False

            logger.info("✅ Token Holder Analysis Complete.")
            return True

        except Exception as e:
            logger.error(f"❌ Error fetching largest accounts from Helius: {e}")
            return False

    def log_failed_token(self, token_mint, token_owner, signature, liquidity, market_cap, reason):
        now = datetime.now()
        date_str = now.strftime("%Y-%m-%d")
        time_str = now.strftime("%H:%M:%S")

        self.excel_utility.save_to_csv(
            self.excel_utility.TOKENS_DIR,
            f"scam_tokens_{date_str}.csv",
            {
                "Timestamp": [f"{date_str} {time_str}"],
                "Signature": [signature],
                "Token Mint": [token_mint],
                "Token Owner": [token_owner],
                "Liquidity (Estimated)": [liquidity],
                "Market Cap": [market_cap],
                "Fail Reason": [reason],
            },
        )

