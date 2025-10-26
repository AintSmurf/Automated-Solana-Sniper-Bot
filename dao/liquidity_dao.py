from services.sql_db_utility import SqlDBUtility
from services.bot_context import BotContext

class LiquidityDAO:
    def __init__(self, ctx: BotContext):
        self.sql_helper: SqlDBUtility = ctx.get("sql_db")
    
    def insert_snapshot(self, token_id: int, data: dict) -> int:
        sql = """
        INSERT INTO liquidity_snapshots 
            (token_id, sol_liq, usdc_liq, usdt_liq, usd1_liq, total_liq, timestamp)
        VALUES (%s, %s, %s, %s, %s, %s, to_timestamp(%s))
        RETURNING id;
        """
        params = (
            token_id,
            data["breakdown"].get("SOL", 0.0),
            data["breakdown"].get("USDC", 0.0),
            data["breakdown"].get("USDT", 0.0),
            data["breakdown"].get("USD1", 0.0),
            data.get("total_liq_usd", 0.0),
            data.get("timestamp", 0.0),
        )
        return self.sql_helper.execute_insert(sql, params)
   
    def insert_pool(self, token_id: int, pool_address: str, dex_source: str) -> int:
        sql = """
        INSERT INTO token_pools (token_id, pool_address, dex_source)
        VALUES (%s, %s, %s)
        ON CONFLICT (pool_address)
        DO UPDATE SET 
            dex_source = EXCLUDED.dex_source,
            created_at = CURRENT_TIMESTAMP
        RETURNING id;
        """
        params = (token_id, pool_address, dex_source)
        return self.sql_helper.execute_insert(sql, params)
    
    def get_pool_address(self, token_address: str):
        sql = """
        SELECT tp.pool_address
        FROM token_pools tp
        INNER JOIN tokens t ON tp.token_id = t.id
        WHERE t.token_address = %s
        """
        params = (token_address,)
        result = self.sql_helper.execute_select(sql, params)
        return result[0]["pool_address"] if result else None



