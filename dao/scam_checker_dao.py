from services.sql_db_utility import SqlDBUtility
from services.bot_context import BotContext
from helpers.framework_utils import get_formatted_date_str

class ScamCheckerDao:

    def __init__(self,ctx:BotContext):
        self.sql_helper:SqlDBUtility = ctx.get("sql_db")
    
    
    def insert_token_results(self, token_id: str, lp_check: bool,holders_check:bool,volume_check:bool,marketcap_check:bool,score:int):
        timestamp = get_formatted_date_str()
        sql = """
            INSERT INTO safety_results (token_id, lp_check, holders_check,volume_check,marketcap_check,score,detected_at)
            VALUES (%s, %s, %s,%s, %s, %s,%s, %s)
            ON CONFLICT (token_address) DO NOTHING
            RETURNING id;
        """
        params = (token_id, lp_check,holders_check,volume_check,marketcap_check,score,timestamp)
        token_id = self.sql_helper.execute_insert(sql, params)
        return token_id
    
