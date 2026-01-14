from services.sql_db_utility import SqlDBUtility
from services.bot_context import BotContext
from datetime import datetime, timezone


class PriceSampleDAO:
    def __init__(self, ctx: BotContext):
        self.sql_helper: SqlDBUtility = ctx.get("sql_db")
    
    def get_samples_by_trade_ids_rows(self, trade_ids: list[int]):
        if not trade_ids:
            return []
        sql = """
            SELECT
                ps.trade_id,
                ps.token_id,
                ps.timestamp AS ts,
                ps.price_usd,
                ps.pnl_percent
            FROM price_samples ps
            WHERE ps.trade_id = ANY(%s)
            ORDER BY ps.trade_id, ps.timestamp;
        """
        return self.sql_helper.execute_select(sql, (trade_ids,))

    def insert_sample( self, trade_id: int, token_id: int, price_usd: float, pnl_percent: float | None = None, ts: datetime | None = None,) -> int:
        sql = """
        INSERT INTO price_samples (trade_id, token_id, timestamp, price_usd, pnl_percent)
        VALUES (%s, %s, %s, %s, %s)
        RETURNING id;
        """
        if ts is None:
            ts = datetime.now(timezone.utc)
        params = (trade_id, token_id, ts, price_usd, pnl_percent)
        return self.sql_helper.execute_insert(sql, params)

    def bulk_insert_samples(self, samples: list[dict]) -> None:
        if not samples:
            return

        sql = """
        INSERT INTO price_samples (trade_id, token_id, timestamp, price_usd, pnl_percent)
        VALUES (%s, %s, %s, %s, %s);
        """
        params_list = []
        for s in samples:
            ts = s.get("timestamp") or datetime.now(timezone.utc)
            params_list.append((
                s["trade_id"],
                s["token_id"],
                ts,
                s["price_usd"],
                s.get("pnl_percent"),
            ))
        self.sql_helper.execute_many(sql, params_list)

    def get_samples_for_trade(self, trade_id: int):
        sql = """
        SELECT id, trade_id, token_id, timestamp, price_usd, pnl_percent
        FROM price_samples
        WHERE trade_id = %s
        ORDER BY timestamp;
        """
        return self.sql_helper.execute_select(sql, (trade_id,))

    def get_samples_for_token_range(
        self,
        token_id: int,
        start_ts: datetime,
        end_ts: datetime,
    ):
        sql = """
        SELECT id, trade_id, token_id, timestamp, price_usd, pnl_percent
        FROM price_samples
        WHERE token_id = %s
          AND timestamp BETWEEN %s AND %s
        ORDER BY timestamp;
        """
        return self.sql_helper.execute_select(sql, (token_id, start_ts, end_ts))
    
