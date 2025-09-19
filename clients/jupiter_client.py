
from config.third_parties import JUPITER_STATION
from services.bot_context import BotContext
from helpers.framework_utils import decimal_to_lamports,lamports_to_decimal,get_payload
from solders.transaction import VersionedTransaction  # type: ignore
import base64



class JupiterClient:
    def __init__(self,ctx:BotContext):
        self.ctx = ctx
        self.logger = ctx.get("logger")
        self.jupiter_requests = ctx.get("jupiter_requests")
        self.swap_payload = get_payload("Swap_token_payload")
  
    def get_quote_dict(self, input_mint:str, output_mint:str, token_amount:float)->dict:
        try:
            self.ctx.get("jupiter_rl").wait()            
            slippage_bps = int(self.ctx.settings["SLPG"]) * 100
            quote_url = f"{JUPITER_STATION['QUOTE_ENDPOINT']}?inputMint={input_mint}&outputMint={output_mint}&amount={token_amount}&slippageBps={slippage_bps}&restrictIntermediateTokens=true"
            quote_response = self.jupiter_requests.get(quote_url)

            if "error" in quote_response:
                self.logger.warning(f"⚠️ Quote attempt failed: {quote_response['error']}")
                return {}
            self.logger.debug(f"Build swap transaction: {quote_response} Success.")
            self.logger.info(f"📦 Jupiter Quote for{output_mint}: In = {quote_response['inAmount']}, Out = {quote_response['outAmount']}")
            token_in = lamports_to_decimal(quote_response['inAmount'],self.ctx.get("helius_client").get_token_decimals(input_mint))
            token_out = lamports_to_decimal(quote_response['outAmount'],self.ctx.get("helius_client").get_token_decimals(output_mint))
            return {"quote_price":token_out/token_in,"inAmount":token_in,"outAmount":token_out,"quote":quote_response}

        except Exception as e:
            self.logger.error(f"❌ Error retrieving quote: {e}")
            return {}
    
    def get_solana_token_worth_in_dollars(self, usd_amount: int) -> float:
        sol_price = float(self.get_sol_price())
        sol_needed  = usd_amount / sol_price
        return decimal_to_lamports(sol_needed, 9)
    
    def get_sol_price(self) -> float:
        self.ctx.get("jupiter_rl").wait()
        response = self.jupiter_requests.get(endpoint=f"{JUPITER_STATION['PRICE']}?ids=So11111111111111111111111111111111111111112")
        return float(response["So11111111111111111111111111111111111111112"]["usdPrice"])

    def get_swap_transaction(self, quote_response: dict):
        try:
            self.ctx.get("jupiter_rl").wait()   
            self.swap_payload["userPublicKey"] = str(self.ctx.get("wallet_client").get_public_key())
            self.swap_payload["quoteResponse"] = quote_response
            swap_response = self.jupiter_requests.post(
                endpoint=JUPITER_STATION["SWAP_ENDPOINT"], payload=self.swap_payload
            )
            swap_txn_base64 = swap_response["swapTransaction"]
            try:
                raw_bytes = base64.b64decode(swap_txn_base64)
                raw_tx = VersionedTransaction.from_bytes(raw_bytes)
                signed_tx = VersionedTransaction(raw_tx.message, [self.ctx.get("wallet_client").get_keypair()])
                self.logger.info( f"Signed transaction for Wallet address: {self.ctx.get("wallet_client").get_private_key()}")
                seralized_tx = bytes(signed_tx)
                signed_tx_base64 = base64.b64encode(seralized_tx).decode("utf-8")
                self.logger.debug(f"signed base64 transaction: {signed_tx_base64}")
                self.logger.info(f"signed base64 transaction")
                try:
                    tx_signature = str(signed_tx.signatures[0])
                    self.logger.info(f"Transaction signature: {tx_signature}")
                except Exception as e:
                    self.logger.error(f"❌ Transaction signature extraction failed: {e}")
            except Exception as e:
                self.logger.error(f"❌ Swap transaction is not valid Base64: {e}")
                return None
            return signed_tx_base64
        except Exception as e:
            self.logger.error(f"❌ Error building swap transaction: {e}")
            return None
    
    def get_token_price(self, mint: str) -> float:
        self.ctx.get("jupiter_rl").wait()   
        endpoint = f"{JUPITER_STATION['PRICE']}?ids={mint}&showExtraInfo=true"
        data = self.jupiter_requests.get(endpoint)
        if mint not in data or "usdPrice" not in data[mint]:
            self.logger.warning(f"No price for {mint}: {data}")
            return None
        return float(data[mint]["usdPrice"])
    
    def get_token_prices(self, mints: list) -> dict[str, float]:
        self.ctx.get("jupiter_rl").wait()
        endpoint = f"{JUPITER_STATION['PRICE']}?ids={','.join(mints)}&showExtraInfo=true"
        data = self.jupiter_requests.get(endpoint)

        prices = {}
        for mint in mints:
            if mint in data and "usdPrice" in data[mint]:
                prices[mint] = float(data[mint]["usdPrice"])
            else:
                self.logger.warning(f"No price for {mint}: {data}")
                prices[mint] = None
        return prices
