from services.sql_db_utility import SqlDBUtility
from services.bot_context import BotContext
from datetime import datetime, timezone

class SignatureDAO:
    def __init__(self, ctx: BotContext):
        self.sql_helper: SqlDBUtility = ctx.get("sql_db")

    def upsert_buy_signature(self, token_id: int, buy_signature: str):
        current_ts = datetime.now(timezone.utc)
        sql = """
            INSERT INTO signatures (token_id, buy_signature, buy_time)
            VALUES (%s, %s, %s)
            ON CONFLICT (token_id)
            DO UPDATE SET
                buy_signature = EXCLUDED.buy_signature,
                buy_time      = EXCLUDED.buy_time;
        """
        self.sql_helper.execute_update(sql, (token_id, buy_signature, current_ts))

    def upsert_sell_signature(self, token_id: int, sell_signature: str):
        current_ts = datetime.now(timezone.utc)
        sql = """
            INSERT INTO signatures (token_id, sell_signature, sell_time)
            VALUES (%s, %s, %s)
            ON CONFLICT (token_id)
            DO UPDATE SET
                sell_signature = EXCLUDED.sell_signature,
                sell_time      = EXCLUDED.sell_time;
        """
        self.sql_helper.execute_update(sql, (token_id, sell_signature, current_ts))
    
    def get_buy_signature(self, token_id: int) -> str | None:
        sql = "SELECT buy_signature FROM signatures WHERE token_id = %s;"
        rows = self.sql_helper.execute_select(sql, (token_id,))
        if not rows:
            return None
        sig = rows[0].get("buy_signature")
        return sig if sig else None
