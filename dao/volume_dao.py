from services.sql_db_utility import SqlDBUtility
from services.bot_context import BotContext

class VolumeDAO:
    def __init__(self, ctx: BotContext):
        self.sql_helper: SqlDBUtility = ctx.get("sql_db")

    def insert_volume_snapshot(self, token_id: int, stats: dict) -> int:
        sql = """
        INSERT INTO token_volumes 
            (token_id, buy_usd, sell_usd, total_usd, buy_count, sell_count, 
             buy_ratio, net_flow, launch_time, launch_volume, delta_volume, snapshot_time)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, to_timestamp(%s), %s, %s, CURRENT_TIMESTAMP)
        RETURNING id;
        """
        params = (
            token_id,
            stats.get("buy_usd", 0.0),
            stats.get("sell_usd", 0.0),
            stats.get("total_usd", 0.0),
            stats.get("buy_count", 0),
            stats.get("sell_count", 0),
            stats.get("buy_ratio", 0.0),
            stats.get("net_flow", 0.0),
            stats.get("launch_time", 0.0),
            stats.get("launch_volume", 0.0),
            stats.get("delta_volume", 0.0),
        )
        return self.sql_helper.execute_insert(sql, params)
