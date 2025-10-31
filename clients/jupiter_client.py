
from config.third_parties import JUPITER_STATION
from config.dex_detection_rules import FEE_WALLETS 
from services.bot_context import BotContext
from helpers.framework_utils import decimal_to_lamports,lamports_to_decimal,get_payload
from solders.transaction import VersionedTransaction  # type: ignore
from solders.system_program import TransferParams, transfer
import random, base64
from solders.pubkey import Pubkey# type: ignore
from solders.instruction import Instruction, AccountMeta
from solders.pubkey import Pubkey
from solders.transaction import VersionedTransaction, Transaction
from solders.message import Message
import requests


LAMPORTS_PER_SOL = 1_000_000_000


class JupiterClient:
    def __init__(self,ctx:BotContext):
        self.ctx = ctx
        self.logger = ctx.get("logger")
        self.jupiter_requests = ctx.get("jupiter_requests")
        self.swap_payload = get_payload("Swap_token_payload")
  
    def get_quote_dict(self, input_mint:str, output_mint:str, token_amount:float, slippage_override: float = None)->dict:
        try:
            self.ctx.get("jupiter_rl").wait()            
            slippage_value = slippage_override if slippage_override is not None else self.ctx.settings["SLPG"]
            slippage_bps = int(slippage_value) * 100
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
                self.logger.info(f"Signed transaction for Wallet: {self.ctx.get('wallet_client').get_public_key()}")
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
    
    def get_swap_transaction_for_sender(self, quote_response: dict) -> str | None:
        try:
            # Respect Jupiter rate limit
            self.ctx.get("jupiter_rl").wait()
            wallet_client = self.ctx.get("wallet_client")
            keypair = wallet_client.get_keypair()
            user_pubkey = Pubkey.from_string(str(wallet_client.get_public_key()))
            self.swap_payload["userPublicKey"] = str(user_pubkey)
            self.swap_payload["quoteResponse"] = quote_response
            self.swap_payload["asLegacyTransaction"] = True 

            swap_response = self.jupiter_requests.post(
                endpoint=JUPITER_STATION["SWAP_ENDPOINT"],
                payload=self.swap_payload,
            )
            swap_txn_base64 = swap_response["swapTransaction"]
            self.logger.debug(f"Raw Jupiter swap response: {swap_response}")

            raw_bytes = base64.b64decode(swap_txn_base64)
            raw_tx = VersionedTransaction.from_bytes(raw_bytes)
            msg_any = raw_tx.message 

            msg: Message = msg_any 

            jup_instructions: list[Instruction] = []
            for ci in msg.instructions:
                program_id = msg.account_keys[ci.program_id_index]

                account_metas = [
                    AccountMeta(
                        pubkey=msg.account_keys[i],
                        is_signer=(i < msg.header.num_required_signatures),
                        is_writable=(
                            i < len(msg.account_keys) - msg.header.num_readonly_unsigned_accounts
                        ),
                    )
                    for i in ci.accounts
                ]

                jup_instructions.append(
                    Instruction(program_id=program_id, data=ci.data, accounts=account_metas)
                )

            tip_wallet_str = random.choice(list(FEE_WALLETS.values()))
            tip_wallet = Pubkey.from_string(tip_wallet_str)
            tip_sol = self._get_dynamic_tip_sol()

            lamports = int(tip_sol * LAMPORTS_PER_SOL)
            tip_ix = transfer(
                TransferParams(
                    from_pubkey=user_pubkey,
                    to_pubkey=tip_wallet,
                    lamports=lamports,
                )
            )
            all_instructions: list[Instruction] = [
                tip_ix,
                *jup_instructions,
            ]
            new_message = Message(
                instructions=all_instructions,
                payer=user_pubkey,
            )
            new_tx = Transaction(
                message=new_message,
                from_keypairs=[keypair],
                recent_blockhash=msg.recent_blockhash
            )

            signed_tx_base64 = base64.b64encode(bytes(new_tx)).decode("utf-8")
            self.logger.info(f"✅ Added {tip_sol:.6f} SOL tip → {tip_wallet_str}")
            return signed_tx_base64

        except Exception as e:
            self.logger.error(f"❌ Error building swap transaction for sender: {e}")
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

    def get_token_worth_in_usd(self, mint: str, token_amount: float) -> float:
        usd_price = self.get_token_price(mint)
        return token_amount * usd_price

    def _get_dynamic_tip_sol(self) -> float:
        try:
            resp = requests.get(
                "https://bundles.jito.wtf/api/v1/bundles/tip_floor",
                timeout=2,
            )
            resp.raise_for_status()
            data = resp.json()
            tip_75 = float(data[0].get("landed_tips_75th_percentile", 0.0))
            tip_sol = max(tip_75, 0.001)
            return tip_sol
        except Exception as e:
            self.logger.warning(f"⚠️ Failed to fetch dynamic Jito tip, falling back to 0.001 SOL: {e}")
            return 0.001