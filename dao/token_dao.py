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
    
