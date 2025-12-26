from services.sql_db_utility import SqlDBUtility
from services.bot_context import BotContext
from helpers.framework_utils import get_formatted_date_str
from typing import Optional
from datetime import datetime
from typing import Iterable, Optional, Literal



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
    
    def produce_summary_results(self, since_ts: str | None = None):
        base_sql = """
        SELECT
            t.token_address,
            s.buy_signature,
            s.sell_signature,
            tr.entry_usd,
            tr.exit_usd,
            tr.pnl_percent,
            tr.trigger_reason,
            sr.score,
            ts.market_cap
        FROM tokens t
        INNER JOIN signatures s      ON t.id = s.token_id
        INNER JOIN trades tr         ON t.id = tr.token_id
        INNER JOIN safety_results sr ON t.id = sr.token_id
        INNER JOIN token_stats ts    ON t.id = ts.token_id
        """
        params = []
        if since_ts:
            base_sql += 'WHERE tr."timestamp" >= %s '
            params.append(since_ts)

        return self.sql_helper.execute_select(base_sql, tuple(params)) or None

    def produce_summary_per_date(self, tz_offset_str: str, since_ts: str | None = None):
        sql = """
        SELECT
            (
                ("timestamp" AT TIME ZONE %s) - INTERVAL '7 hour'
            )::date AS session_date,
            COUNT(*) AS trade_count,
            SUM(pnl_percent) AS total_pnl_percent,
            AVG(pnl_percent) AS avg_pnl_percent,
            SUM(CASE WHEN pnl_percent > 0 THEN 1 ELSE 0 END) AS winning_trades,
            SUM(CASE WHEN pnl_percent < 0 THEN 1 ELSE 0 END) AS losing_trades
        FROM trades
        WHERE 1=1
        """
        params = [tz_offset_str]

        if since_ts:
            sql += ' AND "timestamp" >= %s'
            params.append(since_ts)

        sql += """
        GROUP BY session_date
        ORDER BY session_date;
        """

        return self.sql_helper.execute_select(sql, tuple(params)) or None

    def produce_exit_rule_stats(self, since_ts: str | None = None):
        sql = """
        SELECT
            trigger_reason,
            COUNT(*) AS trade_count,
            AVG(pnl_percent) AS avg_pnl_percent,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY pnl_percent) AS median_pnl_percent,
            PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY pnl_percent) AS p95_pnl_percent,
            SUM(exit_usd - entry_usd) AS total_profit_usd,
            AVG(exit_usd - entry_usd) AS avg_profit_usd
        FROM trades
        WHERE 1=1
        """
        params = []

        if since_ts:
            sql += ' AND "timestamp" >= %s'
            params.append(since_ts)

        sql += " GROUP BY trigger_reason ORDER BY total_profit_usd DESC;"

        return self.sql_helper.execute_select(sql, tuple(params)) or None

    def produce_liquidity_stats(self, since_ts: str | None = None):
        sql = """
        WITH liq_at_buy AS (
            SELECT DISTINCT ON (tr.id)
                tr.id AS trade_id,
                tr.pnl_percent,
                tr.entry_usd,
                tr.exit_usd,
                ls.total_liq
            FROM trades tr
            JOIN liquidity_snapshots ls
              ON ls.token_id = tr.token_id
             AND ls."timestamp" <= tr."timestamp"
            WHERE 1=1
        """
        params = []

        if since_ts:
            sql += ' AND tr."timestamp" >= %s'
            params.append(since_ts)

        sql += """
            ORDER BY tr.id, ls."timestamp" DESC
        )
        SELECT
            CASE
                WHEN total_liq IS NULL      THEN 'unknown'
                WHEN total_liq <  5000      THEN '<5k'
                WHEN total_liq < 10000      THEN '5k-10k'
                WHEN total_liq < 25000      THEN '10k-25k'
                WHEN total_liq < 50000      THEN '25k-50k'
                ELSE '50k+'
            END AS liq_bucket,
            COUNT(*) AS trade_count,
            AVG(pnl_percent) AS avg_pnl_percent,
            SUM(exit_usd - entry_usd) AS total_profit_usd,
            AVG(exit_usd - entry_usd) AS avg_profit_usd
        FROM liq_at_buy
        GROUP BY liq_bucket
        ORDER BY liq_bucket;
        """

        return self.sql_helper.execute_select(sql, tuple(params)) or None

    def produce_safety_score_stats(self, since_ts: str | None = None):
        sql = """
        WITH trade_safety AS (
            SELECT
                tr.entry_usd,
                tr.exit_usd,
                tr.pnl_percent,
                sr.score
            FROM trades tr
            JOIN safety_results sr ON sr.token_id = tr.token_id
            WHERE 1=1
        """
        params = []

        if since_ts:
            sql += ' AND tr."timestamp" >= %s'
            params.append(since_ts)

        sql += """
        )
        SELECT
            CASE
                WHEN score IS NULL THEN 'no_score'
                WHEN score < 25    THEN '0-25'
                WHEN score < 50    THEN '25-50'
                WHEN score < 75    THEN '50-75'
                ELSE '75-100'
            END AS score_bucket,
            COUNT(*) AS trade_count,
            AVG(pnl_percent) AS avg_pnl_percent,
            SUM(exit_usd - entry_usd) AS total_profit_usd
        FROM trade_safety
        GROUP BY score_bucket
        ORDER BY score_bucket;
        """

        return self.sql_helper.execute_select(sql, tuple(params)) or None

    def produce_hold_duration_stats(self, since_ts: str | None = None):
        sql = """
        WITH durations AS (
            SELECT
                tr.entry_usd,
                tr.exit_usd,
                tr.pnl_percent,
                EXTRACT(EPOCH FROM (s.sell_time - s.buy_time)) AS hold_seconds
            FROM trades tr
            JOIN signatures s ON s.token_id = tr.token_id
            WHERE s.sell_time IS NOT NULL
        """
        params = []

        if since_ts:
            sql += ' AND tr."timestamp" >= %s'
            params.append(since_ts)

        sql += """
        )
        SELECT
            CASE
                WHEN hold_seconds <  60  THEN '<1m'
                WHEN hold_seconds < 180  THEN '1-3m'
                WHEN hold_seconds < 600  THEN '3-10m'
                ELSE '10m+'
            END AS hold_bucket,
            COUNT(*) AS trade_count,
            AVG(hold_seconds) AS avg_hold_seconds,
            AVG(pnl_percent) AS avg_pnl_percent,
            SUM(exit_usd - entry_usd) AS total_profit_usd
        FROM durations
        GROUP BY hold_bucket
        ORDER BY hold_bucket;
        """

        return self.sql_helper.execute_select(sql, tuple(params)) or None

    def produce_token_age_stats(self, since_ts: str | None = None):
        sql = """
        WITH ages AS (
            SELECT
                tr.entry_usd,
                tr.exit_usd,
                tr.pnl_percent,
                EXTRACT(EPOCH FROM (tr."timestamp" - tok.detected_at)) AS age_seconds
            FROM trades tr
            JOIN tokens tok ON tok.id = tr.token_id
            WHERE 1=1
        """
        params = []

        if since_ts:
            sql += ' AND tr."timestamp" >= %s'
            params.append(since_ts)

        sql += """
        )
        SELECT
            CASE
                WHEN age_seconds <  10 THEN '0-10s'
                WHEN age_seconds <  20 THEN '10-20s'
                WHEN age_seconds <  30 THEN '20-30s'
                ELSE '30s+'
            END AS age_bucket,
            COUNT(*) AS trade_count,
            AVG(age_seconds) AS avg_age_seconds,
            AVG(pnl_percent) AS avg_pnl_percent,
            SUM(exit_usd - entry_usd) AS total_profit_usd
        FROM ages
        GROUP BY age_bucket
        ORDER BY age_bucket;
        """

        return self.sql_helper.execute_select(sql, tuple(params)) or None

    def list_trigger_reasons(self, since_ts: str | None = None):
        sql = """
        SELECT DISTINCT tr.trigger_reason
        FROM trades tr
        WHERE tr.trigger_reason IS NOT NULL
        """
        params = []
        if since_ts:
            sql += ' AND tr."timestamp" >= %s'
            params.append(since_ts)

        sql += " ORDER BY tr.trigger_reason;"

        rows = self.sql_helper.execute_select(sql, tuple(params)) or []
        return [r[0] for r in rows]

    def fetch_trades_with_features(
        self,
        since_ts: Optional[str] = None,
        until_ts: Optional[str] = None,
        pnl_lte: Optional[float] = None,  
        pnl_gte: Optional[float] = None,
        trigger_reasons: Optional[Iterable[str]] = None, 
        trigger_ilike: Optional[str] = None,          
        status: Optional[str] = None,
        simulation: Optional[bool] = None,
        safety_score_lte: Optional[float] = None,
        safety_score_gte: Optional[float] = None,
        total_liq_lte: Optional[float] = None,
        total_liq_gte: Optional[float] = None,
        net_flow_lte: Optional[float] = None,
        net_flow_gte: Optional[float] = None,
        delta_volume_lte: Optional[float] = None,
        delta_volume_gte: Optional[float] = None,

        mode: Literal["detail", "summary_by_reason", "summary_by_liq_bucket"] = "detail",
        limit: Optional[int] = None,
    ):
        params: list = []
        where = ["1=1"]
        if since_ts:
            where.append('tr."timestamp" >= %s')
            params.append(since_ts)
        if until_ts:
            where.append('tr."timestamp" < %s')
            params.append(until_ts)

        if pnl_lte is not None:
            where.append("tr.pnl_percent <= %s")
            params.append(pnl_lte)
        if pnl_gte is not None:
            where.append("tr.pnl_percent >= %s")
            params.append(pnl_gte)

        if status:
            where.append("tr.status = %s")
            params.append(status)

        if simulation is not None:
            where.append("tr.simulation = %s")
            params.append(simulation)

        if trigger_ilike:
            where.append("tr.trigger_reason ILIKE %s")
            params.append(trigger_ilike)

        if trigger_reasons:
            where.append("tr.trigger_reason = ANY(%s)")
            params.append(list(trigger_reasons))
        base_sql = f"""
        WITH base AS (
            SELECT tr.*
            FROM trades tr
            WHERE {" AND ".join(where)}
        ),
        feats AS (
            SELECT
                tr.id          AS trade_id,
                tr.token_id,
                tr."timestamp" AS trade_ts,
                tr.trade_type,
                tr.entry_usd,
                tr.exit_usd,
                tr.pnl_percent,
                tr.trigger_reason,
                tr.status,
                tr.simulation,

                ts.market_cap,
                ts.holders_count,

                liq.total_liq,
                liq.sol_liq,
                liq.usdc_liq,
                liq.usdt_liq,
                liq.usd1_liq,

                vol.net_flow,
                vol.delta_volume,
                vol.buy_usd,
                vol.sell_usd,
                vol.total_usd,
                vol.buy_count,
                vol.sell_count,
                vol.buy_ratio,

                sr.score AS safety_score

        FROM base tr
        LEFT JOIN token_stats ts           ON ts.token_id  = tr.token_id
        LEFT JOIN liquidity_snapshots liq  ON liq.token_id = tr.token_id
        LEFT JOIN token_volumes vol        ON vol.token_id = tr.token_id
        LEFT JOIN safety_results sr        ON sr.token_id  = tr.token_id
        )

        """
        feat_where = ["1=1"]
        feat_params: list = []

        def add_feat(cond: str, val):
            feat_where.append(cond)
            feat_params.append(val)

        if safety_score_lte is not None: add_feat("safety_score <= %s", safety_score_lte)
        if safety_score_gte is not None: add_feat("safety_score >= %s", safety_score_gte)

        if total_liq_lte is not None: add_feat("total_liq <= %s", total_liq_lte)
        if total_liq_gte is not None: add_feat("total_liq >= %s", total_liq_gte)

        if net_flow_lte is not None: add_feat("net_flow <= %s", net_flow_lte)
        if net_flow_gte is not None: add_feat("net_flow >= %s", net_flow_gte)

        if delta_volume_lte is not None: add_feat("delta_volume <= %s", delta_volume_lte)
        if delta_volume_gte is not None: add_feat("delta_volume >= %s", delta_volume_gte)

        # ---- outputs ----
        if mode == "detail":
            sql = base_sql + f"""
            SELECT *
            FROM feats
            WHERE {" AND ".join(feat_where)}
            ORDER BY trade_ts DESC
            """
            if limit is not None:
                sql += " LIMIT %s"
                feat_params.append(limit)

        elif mode == "summary_by_reason":
            sql = base_sql + f"""
            SELECT
              COALESCE(trigger_reason, 'unknown') AS trigger_reason,
              COUNT(*) AS trade_count,
              AVG(pnl_percent) AS avg_pnl_percent,
              SUM(exit_usd - entry_usd) AS total_profit_usd,
              AVG(exit_usd - entry_usd) AS avg_profit_usd
            FROM feats
            WHERE {" AND ".join(feat_where)}
            GROUP BY 1
            ORDER BY trade_count DESC;
            """

        elif mode == "summary_by_liq_bucket":
            sql = base_sql + f"""
            SELECT
              CASE
                WHEN total_liq IS NULL      THEN 'unknown'
                WHEN total_liq <  5000      THEN '<5k'
                WHEN total_liq < 10000      THEN '5k-10k'
                WHEN total_liq < 25000      THEN '10k-25k'
                WHEN total_liq < 50000      THEN '25k-50k'
                ELSE '50k+'
              END AS liq_bucket,
              COUNT(*) AS trade_count,
              AVG(pnl_percent) AS avg_pnl_percent,
              SUM(exit_usd - entry_usd) AS total_profit_usd,
              AVG(exit_usd - entry_usd) AS avg_profit_usd
            FROM feats
            WHERE {" AND ".join(feat_where)}
            GROUP BY 1
            ORDER BY 1;
            """
        else:
            raise ValueError("bad mode")

        all_params = tuple(params + feat_params)
        return self.sql_helper.execute_select(sql, all_params) or None