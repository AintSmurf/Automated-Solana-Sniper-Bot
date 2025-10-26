from services.sql_db_utility import SqlDBUtility
from services.bot_context import BotContext
from datetime import datetime, timezone

class SignatureDAO:
    def __init__(self, ctx: BotContext):
        self.sql_helper: SqlDBUtility = ctx.get("sql_db")

    def insert_signature(self, token_id, buy_signature=None, sell_signature=None):
        current_ts = datetime.now(timezone.utc)
        sql = """
            INSERT INTO signatures (token_id, buy_signature, sell_signature, buy_time)
            VALUES (%s, %s, %s, %s)
            RETURNING id;
        """
        params = (token_id, buy_signature, sell_signature, current_ts)
        return self.sql_helper.execute_insert(sql, params)

    def update_buy_signature(self, token_id, buy_signature):
        current_ts = datetime.now(timezone.utc)
        sql = """
            UPDATE signatures
            SET buy_signature = %s, buy_time = %s
            WHERE token_id = %s;
        """
        self.sql_helper.execute_update(sql, (buy_signature, current_ts, token_id))

    def update_sell_signature(self, token_id, sell_signature):
        current_ts = datetime.now(timezone.utc)
        sql = """
            UPDATE signatures
            SET sell_signature = %s, sell_time = %s
            WHERE token_id = %s;
        """
        self.sql_helper.execute_update(sql, (sell_signature, current_ts, token_id))
