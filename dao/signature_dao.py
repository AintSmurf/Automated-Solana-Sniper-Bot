from services.sql_db_utility import SqlDBUtility
from services.bot_context import BotContext
from datetime import datetime, timezone


class SignatureDAO:
    def __init__(self, ctx: BotContext):
        self.sql_helper: SqlDBUtility = ctx.get("sql_db")

    def upsert_buy_signature(self,token_id: int,buy_signature: str,trade_id: int | None = None,):
        current_ts = datetime.now(timezone.utc)
        sql = """
            INSERT INTO signatures (token_id, buy_signature, buy_time, trade_id)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (token_id)
            DO UPDATE SET
                buy_signature = EXCLUDED.buy_signature,
                buy_time      = EXCLUDED.buy_time,
                trade_id      = COALESCE(EXCLUDED.trade_id, signatures.trade_id);"""
        self.sql_helper.execute_update(
            sql,
            (token_id, buy_signature, current_ts, trade_id),
        )

    def upsert_sell_signature( self, token_id: int, sell_signature: str, trade_id: int | None = None,):
        current_ts = datetime.now(timezone.utc)
        sql = """
            INSERT INTO signatures (token_id, sell_signature, sell_time, trade_id)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (token_id)
            DO UPDATE SET
                sell_signature = EXCLUDED.sell_signature,
                sell_time      = EXCLUDED.sell_time,
                trade_id       = COALESCE(EXCLUDED.trade_id, signatures.trade_id);
        """
        self.sql_helper.execute_update(
            sql,
            (token_id, sell_signature, current_ts, trade_id),
        )

    def get_buy_signature(self, token_id: int) -> str | None:
        sql = "SELECT buy_signature FROM signatures WHERE token_id = %s;"
        rows = self.sql_helper.execute_select(sql, (token_id,))
        if not rows:
            return None
        sig = rows[0].get("buy_signature")
        return sig if sig else None

    def attach_trade_id_by_token(self, token_id: int, trade_id: int) -> None:
        sql = """
            UPDATE signatures
            SET trade_id = %s
            WHERE token_id = %s
              AND trade_id IS NULL;
        """
        self.sql_helper.execute_update(sql, (trade_id, token_id))

    def attach_trade_id_by_buy_signature(self, buy_signature: str, trade_id: int) -> None:
        sql = """
            UPDATE signatures
            SET trade_id = %s
            WHERE buy_signature = %s;
        """
        self.sql_helper.execute_update(sql, (trade_id, buy_signature))

    def attach_trade_id_by_sell_signature(self, sell_signature: str, trade_id: int) -> None:
        sql = """
            UPDATE signatures
            SET trade_id = %s
            WHERE sell_signature = %s;
        """
        self.sql_helper.execute_update(sql, (trade_id, sell_signature))