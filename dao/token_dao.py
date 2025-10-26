from services.sql_db_utility import SqlDBUtility
from services.bot_context import BotContext
from helpers.framework_utils import get_formatted_date_str


class TokenDAO:
    def __init__(self, ctx: BotContext):
        self.sql_helper: SqlDBUtility = ctx.get("sql_db")

    def insert_new_token(self, signature: str, token_mint: str):
        timestamp = get_formatted_date_str()
        sql = """
            INSERT INTO tokens (token_address, signature, detected_at)
            VALUES (%s, %s, %s)
            ON CONFLICT (token_address) DO NOTHING
            RETURNING id;
        """
        params = (token_mint, signature, timestamp)
        return self.sql_helper.execute_insert(sql, params)

    def get_or_create_token(self, token_mint: str, signature: str | None):
        """Return token.id if exists, otherwise create it."""
        sql = "SELECT id FROM tokens WHERE token_address = %s;"
        result = self.sql_helper.execute_select(sql, (token_mint,))
        if result:
            return result[0][0]

        return self.insert_new_token(signature or "SIMULATED", token_mint)

    def insert_token_stats(self, token_id: int, marketcap: float, holders: int):
        sql = """
            INSERT INTO token_stats (token_id, market_cap, holders_count)
            VALUES (%s, %s, %s)
            RETURNING id;
        """
        params = (token_id, marketcap, holders)
        return self.sql_helper.execute_insert(sql, params)

    def get_token_id_by_address(self, token_address: str):
        sql = "SELECT id FROM tokens WHERE token_address = %s;"
        res = self.sql_helper.execute_select(sql, (token_address,))
        return res[0][0] if res else None
