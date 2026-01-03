from services.bot_context import BotContext






class SolanaManager:
    def __init__(self, ctx: BotContext):
        self.ctx = ctx
    
    def get_wallet_balances(self) -> list[dict]:
        return self.ctx.get("wallet_client").get_account_balances()

    def buy(self, input_mint: str, output_mint: str, usd_amount: int, sim: bool) -> str:
        return self.ctx.get("trader").buy(input_mint,output_mint,usd_amount,sim)
    
    def sell(self, input_mint: str, output_mint: str) -> dict:
        return self.ctx.get("trader").sell(input_mint,output_mint)
   
    def get_token_supply(self, mint_address: str) -> float:
        return self.ctx.get("helius_client").get_token_supply(mint_address)

    def get_token_marketcap(self, token_mint: str) -> float:
        try:
            supply = self.ctx.get("helius_client").get_token_supply(token_mint)
            price = self.ctx.get("jupiter_client").get_token_price(token_mint)
            return price* supply
        except Exception as e:
            self.logger.error(f"error retriving market cap {e}")

    def get_recent_transactions_signatures_for_token(self, token_mint: str,until:str=None,before:str=None) -> list[str]:
        txs = self.ctx.get("helius_client").get_recent_transactions_signatures_for_token(token_mint,until,before)
        return [t["signature"] for t in txs if isinstance(t, dict) and "signature" in t]
    
    def get_token_age(self, mint_address: str)->int:
        return self.ctx.get("helius_client").get_token_age(mint_address)
    
    def analyze_liquidty(self, transaction, token_mint: str,min_liq:float) -> bool:
        return self.ctx.get("liquidity_analyzer").analyze_liquidty(transaction, token_mint,min_liq)

    def first_phase_tests(self,token_address:str)->bool:
        return self.ctx.get("scam_checker").first_phase_tests(token_address)
    
    def extract_token_mint(self,tx_data:dict)->str:
        return self.ctx.get("liquidity_analyzer").extract_token_mint(tx_data)

    def get_transaction_data(self,signature:str)->dict:
        return self.ctx.get("helius_client").get_transaction(signature) 
    
    def second_phase_tests(self, token_mint:str, signature:str, market_cap:float)->dict:
        return self.ctx.get("scam_checker").second_phase_tests(token_mint, signature, market_cap)


    