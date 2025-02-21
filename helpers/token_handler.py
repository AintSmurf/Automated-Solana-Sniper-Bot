import requests
import base64
from solana.rpc.api import Client
from solders.keypair import Keypair
from utilities.credentials_utility import CredentialsUtility
from utilities.requests_utility import RequestsUtility
from helpers.logging_handler import LoggingHandler
from helpers.framework_helper import get_payload
from config.urls import HELIUS_URL
from config.urls import JUPITER_STATION


# set up logger
logger = LoggingHandler.get_logger()


class TokenHandler:
    def __init__(self):
        logger.info("Initializing Token_Handler class ...")
        credentials_utility = CredentialsUtility()
        self.helius_requests = RequestsUtility(HELIUS_URL["BASE_URL"])
        self.jupiter_requests = RequestsUtility(JUPITER_STATION["BASE_URL"])
        self.api_key = credentials_utility.get_helius_api_key()
        self._private_key_solana = credentials_utility.get_solana_private_wallet_key()
        self.url = HELIUS_URL["BASE_URL"] + self.api_key["API_KEY"]
        self.swap_payload = get_payload("Swap_token_payload")
        self.transaction_simulation_paylod = get_payload("Transaction_simulation")
        self.client = Client(self.url, timeout=30)
        self.keypair = Keypair.from_base58_string(
            self._private_key_solana["SOLANA_PRIVATE_KEY"]
        )

    def get_swap_transaction(self, input_mint, output_mint, amount, slippage=20):
        """Get a swap transaction from Jupiter API (Raydium/Orca)"""
        try:
            quote_url = f"{JUPITER_STATION['QUOTE_ENDPOINT']}?inputMint={input_mint}&outputMint={output_mint}&amount={amount}&slippageBps={slippage}"
            quote_response = self.jupiter_requests.get(quote_url)
            if "error" in quote_response:
                logger.warning(f"⚠️ Error getting quote: {quote_response['error']}")
                return None

            logger.info("retrived the quote response ...")
            # Step 2: Get the Transaction Payload
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
            logger.info(f"✅ Built swap transaction (Base64)")
            logger.debug(f"✅ Built swap transaction (Base64): {swap_txn_base64}")

            return swap_txn_base64

        except Exception as e:
            logger.error(f"❌ Error building swap transaction: {e}")

    def simulate_transaction(self, transaction_base64):
        """Simulate a transaction using Helius RPC"""
        self.transaction_simulation_paylod["params"] = [
            transaction_base64,
            {"encoding": "base64"},
        ]

        try:
            response = self.helius_requests.post(
                endpoint=self.api_key["API_KEY"],
                payload=self.transaction_simulation_paylod,
            )
            logger.debug(f"Transaction Simulation Response: {response}")

            if "error" in response:
                logger.warning(f"⚠️ Simulation failed: {response['error']}")
                return False

            return response["result"]

        except Exception as e:
            logger.error(f"❌ Error simulating transaction: {e}")
            return False

    def is_honeypot(self, token_mint, amount):
        solana_mint = "So11111111111111111111111111111111111111112"
        transaction_base64 = self.get_swap_transaction(token_mint, solana_mint, amount)

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
            "custom program error: 0x26",
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
