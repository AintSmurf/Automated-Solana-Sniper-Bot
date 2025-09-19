from services.bot_context import BotContext
from config.third_parties import BIRDEYE

class BirdeyeClient():
    def __init__(self, ctx:BotContext):
        self.logger = ctx.get("logger")
        self.bird_api_key = ctx.api_keys.get("bird_eye")
        self.birdeye_requests = ctx.get("birdye_requests")
    
    def get_token_price_paid(self, token_mint: str) -> float:
        try:
            headers = {
                "accept": "application/json",
                "x-chain": "solana",
                "X-API-KEY": self.bird_api_key,}
            response = self.birdeye_requests.get(endpoint=f"{BIRDEYE['PRICE']}{token_mint}", headers=headers)
            self.logger.debug(f"response: {response.json()}")
            return response.json()["data"]["value"]
        except Exception as e:
            self.logger.error(f"failed to retrive token price: {e}")
            return 0
       
    
    def get_liqudity(self, token_mint: str) -> float:
        try:
            headers = {
                "accept": "application/json",
                "x-chain": "solana",
                "X-API-KEY": self.bird_api_key,}
            response = self.birdeye_requests.get(endpoint=f"{BIRDEYE['PRICE']}{token_mint}", headers=headers)
            self.logger.debug(f"response: {response.json()}")
            return response.json()["data"]["liquidity"]
        except Exception as e:
            self.logger.error(f"failed to retrive liquidity: {e}")
            return 0