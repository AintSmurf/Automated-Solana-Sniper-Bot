from solders.keypair import Keypair
from solana.rpc.api import Client
import base58
from services.bot_context import BotContext
from helpers.framework_utils import calculate_tokens



class WalletClient:
    def __init__(self, ctx: BotContext):
        self.ctx = ctx
        self.logger = ctx.get("logger")
        wallet_key = ctx.api_keys.get("wallet_key")
        self.account: Keypair | None = None
        self.private_key: str | None = None
        if wallet_key:
            self.set_private_key(wallet_key)

    def fund_devnet_wallet(self, amount: int = 1_000_000_000, min_balance: int = 500_000_000)->str:
        if not self.account:
            raise RuntimeError("Wallet not initialized. Call create_wallet() first.")

        faucet_client = Client("https://api.devnet.solana.com")
        balance_resp = faucet_client.get_balance(self.account.pubkey())
        current_balance = balance_resp.value or 0

        if current_balance < min_balance:
            sig = faucet_client.request_airdrop(self.account.pubkey(), amount)
            self.logger.info(f"💧 Airdrop requested: {sig.value}")
            return sig.value
        else:
            self.logger.info("✅ Wallet already funded above min balance.")
            return None

    def confirm_transaction(self, signature: str)->str:
        """Confirm a transaction by its signature."""
        try:
            self.client = Client(f"{self.ctx.get("helius_client")}{self.ctx.api_keys["helius"]}")
            return self.client.confirm_transaction(signature)
        except Exception as e:
            self.logger.error(f"❌ Error confirming transaction {signature}: {e}")
            return None

    def run_full_flow(self)->dict:
        """Create wallet, fund it on devnet, confirm airdrop."""
        if not self.account:
            self.create_wallet()

        signature = self.fund_devnet_wallet()
        result = self.confirm_transaction(signature) if signature else None

        return {
            "publicKey": self.get_public_key(),
            "privateKey": self.get_private_key(),
            "txSignature": signature,
            "confirmation": result,
        }

    def create_wallet(self)->dict:
        self.account = Keypair()
        self.private_key = base58.b58encode(self.account.secret()).decode("utf-8")
        return {"publicKey": str(self.account.pubkey()), "privateKey": self.private_key}

    def set_private_key(self, private_key_b58: str)->None:
        self.private_key = private_key_b58
        self.account = Keypair.from_base58_string(private_key_b58)
        self.logger.info(f"🔑 Wallet loaded: {self.account.pubkey()}")

    def get_public_key(self)->str:
        return str(self.account.pubkey()) if self.account else ""

    def get_private_key(self)->str:
        return self.private_key or ""
    
    def get_account_balances(self) -> list[dict]:
        try:
            token_balances = calculate_tokens(self.ctx.get("helius_client").get_token_accounts_by_owner(self.get_public_key()))
            sol_balance = self.ctx.get("helius_client").get_balance(self.get_public_key())
            token_balances.insert(0, {"token_mint": "SOL", "balance": sol_balance})
            return [b for b in token_balances if b["balance"] > 0]
        except Exception as e:
            self.logger.error(f"❌ Failed to fetch balances: {e}", exc_info=True)
            return []
    
    def get_keypair(self) -> Keypair:
        """Return the Keypair object for signing transactions."""
        if not self.account:
            raise RuntimeError("Wallet not initialized. Call set_private_key() or create_wallet() first.")
        return self.account