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
from spl.token.instructions import get_associated_token_address
from config.urls import HELIUS_URL, JUPITER_STATION, RAYDIUM
import struct
from solana.transaction import Transaction
from config.urls import JUPITER_STATION
from helpers.framework_manager import get_payload
import base64
import math
import requests


# Set up logger
logger = LoggingHandler.get_logger()


class SolanaHandler:
    def __init__(self):
        self.helius_requests = RequestsUtility(HELIUS_URL["BASE_URL"])
        credentials_utility = CredentialsUtility()
        self.raydium_requests = RequestsUtility(RAYDIUM["BASE_URL"])
        self.jupiter_requests = RequestsUtility(JUPITER_STATION["BASE_URL"])
        self.transaction_simulation_paylod = get_payload("Transaction_simulation")
        self.swap_payload = get_payload("Swap_token_payload")
        self.liquidity_payload = get_payload("Liquidity_payload")
        self.send_transaction_payload = get_payload("Send_transaction")
        self.api_key = credentials_utility.get_helius_api_key()
        self._private_key_solana = credentials_utility.get_solana_private_wallet_key()
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

    def send_transaction(
        self, input_mint: str, output_mint: str, usd_amount: int
    ) -> None:
        logger.info(
            f"🔄 Initiating buy order for {usd_amount}$ worth\ntoken_bought:{output_mint}\ntoken_sold:{input_mint}"
        )
        try:
            token_amount = self.get_solana_token_worth_in_dollars(usd_amount)
            qoute = self.get_quote(input_mint, output_mint, token_amount)
            txn_64 = self.get_swap_transaction(qoute)
            self.send_transaction_payload["params"][0] = txn_64
            self.send_transaction_payload["id"] = self.id
            self.id += 1
            response = self.helius_requests.post(
                self.api_key["API_KEY"], payload=self.send_transaction_payload
            )
            logger.info(response)
        except Exception as e:
            logger.error(f"❌ Failed to place buy order: {e}")

    def get_sol_price(self) -> float:
        response = self.jupiter_requests.get(
            "/price/v2?ids=So11111111111111111111111111111111111111112"
        )
        return float(
            response["data"]["So11111111111111111111111111111111111111112"]["price"]
        )

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

    def get_quote(
        self,
        input_mint,
        output_mint,
        amount=1000,
        slippage=5,
        retries=3,
    ):
        for attempt in range(retries):
            try:
                quote_url = f"{JUPITER_STATION['QUOTE_ENDPOINT']}?inputMint={input_mint}&outputMint={output_mint}&amount={amount}&slippageBps={slippage}"
                quote_response = self.jupiter_requests.get(quote_url)

                if "error" in quote_response:
                    logger.warning(
                        f"⚠️ Quote attempt {attempt + 1} failed: {quote_response['error']}"
                    )
                else:
                    logger.info(
                        f"✅ Successfully retrieved quote on attempt {attempt + 1}."
                    )
                    logger.debug(
                        f"build swap transaction:{quote_response} Successfull."
                    )
                    return quote_response
            except Exception as e:
                logger.error(f"❌ Error retrieving quote: {e} Logs {quote_response}")
        return None

    def get_swap_transaction(self, quote_response: dict):
        """Get a swap transaction from Jupiter API (Raydium/Orca)"""
        if not quote_response or "error" in quote_response:
            logger.error(f"❌ There is an error in quote: {quote_response}")
            return None

        try:
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

    def is_honeypot(
        self,
        token_mint: str,
    ):
        base_mint = "So11111111111111111111111111111111111111112"
        quote = self.get_quote(token_mint, base_mint, 10000)
        transaction_base64 = self.get_swap_transaction(quote)

        if not transaction_base64:
            logger.warning(
                f"⚠️ Could not build swap transaction for token {token_mint}."
            )
            return True

        simulation_result = self.simulate_transaction(transaction_base64)

        if not simulation_result:
            logger.warning(
                f"⚠️ Token {token_mint} is likely a honeypot (Simulation failed)."
            )
            return True

        logs = simulation_result.get("value", {}).get("logs", [])

        honeypot_errors = [
            "sale not allowed",
            "transaction blocked",
            "InvalidSplTokenProgram",
        ]

        for log in logs:
            for error in honeypot_errors:
                if error in log.lower():
                    logger.warning(f"⚠️ Honeypot detected! Error: {error}")
                    return True

        jupiter_errors = [
            "panicked at programs/nostd-token/src",
            "range end index 64 out of range",
            "SBF program panicked",
        ]

        for log in logs:
            for error in jupiter_errors:
                if error in log.lower():
                    logger.warning(
                        f"⚠️ Jupiter error detected (NOT a honeypot)! Error: {error}"
                    )
                    return False

        logger.info(f"✅ Token {token_mint} passed honeypot check.")
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

    def transaction_validtor(self):
        pass

    def get_token_supply(self, mint_address: str) -> float:
        """Fetch total token supply from Solana RPC and scale it correctly."""
        try:
            token_mint = Pubkey.from_string(mint_address)
            response = self.client.get_token_supply(token_mint)
            if response.value:
                supply = float(response.value.ui_amount)
                decimals = int(response.value.decimals)
                return supply / (10**decimals)

        except Exception as e:
            print(f"❌ Error fetching token supply: {e}")

        return 0

    def get_raydium_marketcap(self, token_mint: str) -> float:
        try:

            self.liquidity_payload["mint1"] = token_mint
            response_data = self.raydium_requests.get(
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

    def get_raydium_liquidity(self, token_mint: str) -> float:
        self.liquidity_payload["mint1"] = token_mint
        try:
            response_data = self.raydium_requests.get(
                endpoint=RAYDIUM["LIQUIDITY"], payload=self.liquidity_payload
            )

            if response_data.get("data") and response_data["data"].get("data"):
                pool_data = response_data["data"]["data"][0]
                tvl = float(pool_data.get("tvl", 0))
                return tvl

        except Exception as e:
            logger.error(f"❌ Error fetching liquidity: {e}")

        return 0
