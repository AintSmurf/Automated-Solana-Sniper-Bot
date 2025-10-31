from services.sql_db_utility import SqlDBUtility
from services.bot_context import BotContext
from helpers.framework_utils import get_formatted_date_str
from typing import Optional
from datetime import datetime


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
    
    def get_closed_poisitons(self):
        sql='''
        SELECT t.token_address,s.buy_signature ,s.sell_signature ,t2.entry_usd ,t2.exit_usd ,t2.pnl_percent ,t2.trigger_reason 
        FROM tokens t
        INNER JOIN signatures s ON t.id = s.token_id 
        INNER join trades t2 on t.id = t2.token_id  
        '''
        res = self.sql_helper.execute_select(sql)
        return res if res else None
    
    def produce_summary_results(self):
        sql='''
        SELECT t.token_address ,s.buy_signature ,s.sell_signature ,t2.entry_usd ,t2.exit_usd ,t2.pnl_percent ,t2.trigger_reason,t3.score,t4.market_cap 
        FROM tokens t
        INNER JOIN signatures s ON t.id = s.token_id 
        INNER join trades t2 on t.id = t2.token_id
        INNER join safety_results t3 on t.id = t3.token_id
        INNER join token_stats t4 on t.id = t4.token_id
        '''
        res = self.sql_helper.execute_select(sql)
        return res if res else None

    def produce_summary_per_date(self, tz_offset_str: str):
        sql = '''
        SELECT
            (
                ("timestamp" AT TIME ZONE %s) - INTERVAL '7 hour'
            )::date AS session_date,
            COUNT(*)                           AS trade_count,
            SUM(pnl_percent)                   AS total_pnl_percent,
            AVG(pnl_percent)                   AS avg_pnl_percent,
            SUM(CASE WHEN pnl_percent > 0 THEN 1 ELSE 0 END) AS winning_trades,
            SUM(CASE WHEN pnl_percent < 0 THEN 1 ELSE 0 END) AS losing_trades
        FROM trades
        GROUP BY session_date
        ORDER BY session_date;
        '''
        res = self.sql_helper.execute_select(sql, (tz_offset_str,))
        return res if res else None

    def fetch_mint_signature(
            self,
            trigger_reason: Optional[str] = None,
            from_ts: Optional[datetime] = None,
            to_ts: Optional[datetime] = None,
        ):
            if trigger_reason is None and from_ts is None and to_ts is None:
                sql = '''
                    SELECT signature, token_address
                    FROM tokens
                '''
                res = self.sql_helper.execute_select(sql)
                return res if res else None
            sql = '''
                SELECT DISTINCT
                    t.signature,
                    t.token_address
                FROM tokens t
                INNER JOIN trades s ON t.id = s.token_id
                WHERE 1=1
            '''
            params = []

            if trigger_reason is not None:
                sql += " AND s.trigger_reason = %s"
                params.append(trigger_reason)

            if from_ts is not None:
                sql += " AND s.\"timestamp\" >= %s"
                params.append(from_ts)

            if to_ts is not None:
                sql += " AND s.\"timestamp\" < %s"
                params.append(to_ts)

            sql += " ORDER BY t.token_address"

            res = self.sql_helper.execute_select(sql, tuple(params))
            return res if res else None