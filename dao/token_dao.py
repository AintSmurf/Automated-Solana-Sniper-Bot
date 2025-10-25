from services.sql_db_utility import SqlDBUtility
from services.bot_context import BotContext
from helpers.framework_utils import get_formatted_date_str

class TokenDAO:

    def __init__(self,ctx:BotContext):
        self.sql_helper:SqlDBUtility = ctx.get("sql_db")
    
    
    def insert_new_token(self, signature: str, token_mint: str):
        timestamp = get_formatted_date_str()
        sql = """
            INSERT INTO tokens (token_address, signature, detected_at)
            VALUES (%s, %s, %s)
            ON CONFLICT (token_address) DO NOTHING
            RETURNING id;
        """
        params = (token_mint, signature,timestamp)
        token_id = self.sql_helper.execute_insert(sql, params)
        return token_id
    
    def insert_token_stats(self,token_id:int,marketcap:float,total_liquidity:float):
        sql = """
            INSERT INTO token_stats (token_id, market_cap, liquidity_usd)
            VALUES (%s, %s, %s)
            ON CONFLICT (token_address) DO NOTHING
            RETURNING id;
        """
        params = (token_id,marketcap, total_liquidity)
        token_id = self.sql_helper.execute_insert(sql, params)
        return token_id
   
    def get_token_id_by_address(self,token_address:str):
        sql = """
            SELECT id from tokens t where t.token_address = %s
        """
        params = (token_address,)
        token_id = self.sql_helper.execute_select(sql, params)
        return token_id[0][0]

