from services.sql_db_utility import SqlDBUtility
from services.bot_context import BotContext
from datetime import datetime, timezone



class TradeDAO:
    def __init__(self, ctx: BotContext):
        self.sql_helper: SqlDBUtility = ctx.get("sql_db")
    
    def get_buy_trades_for_backtest_rows(
        self,
        config_id: int,
        start_ts: str,
        end_ts: str,
        simulation: bool = True,
    ):
        sql = """
            SELECT
                tr.id                AS trade_id,
                tr.token_id,
                tok.token_address,
                tr.entry_usd,
                tr.exit_usd,
                tr.pnl_percent       AS live_pnl_percent,
                tr.trade_type,
                tr.simulation,
                tr.status,
                tr.timestamp         AS entry_time,
                tr.config_id,
                COALESCE(sr.score, 0) AS safety_score,
                ts.market_cap
            FROM trades tr
            JOIN tokens tok ON tok.id = tr.token_id
            LEFT JOIN safety_results sr ON sr.id = tr.safety_result_id
            LEFT JOIN token_stats ts ON ts.token_id = tr.token_id
            WHERE tr.config_id = %s
            AND tr.simulation = %s
            AND tr.trade_type = 'BUY'
            AND tr.timestamp >= %s
            AND tr.timestamp < %s
            ORDER BY tr.timestamp;
        """
        return self.sql_helper.execute_select(sql, (config_id, simulation, start_ts, end_ts))

    def insert_trade(
            self,
            token_id,
            trade_type,
            entry_usd,
            simulation=False,
            status=None,
            confirmed_at=None,
            finalized_at=None,
            config_id=None,
            safety_result_id=None,
            volume_snapshot_id=None,
        ):
            current_ts = datetime.now(timezone.utc)

            sql = """
                INSERT INTO trades (
                    token_id,
                    trade_type,
                    entry_usd,
                    simulation,
                    status,
                    confirmed_at,
                    finalized_at,
                    timestamp,
                    config_id,
                    safety_result_id,
                    volume_snapshot_id
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id;
            """
            params = (
                token_id,
                trade_type,
                entry_usd,
                simulation,
                status,
                confirmed_at,          
                finalized_at,          
                current_ts,
                config_id,            
                safety_result_id,      
                volume_snapshot_id,
            )
            return self.sql_helper.execute_insert(sql, params)

    def get_trade_by_signature(self, signature: str):
        sql = "SELECT * FROM trades WHERE signature = %s;"
        rows = self.sql_helper.execute_select(sql, (signature,))
        return rows[0] if rows else None

    def get_trade_by_token(self, token_mint: str):
        sql = """
            SELECT t.*
            FROM trades t
            JOIN tokens tok ON tok.id = t.token_id
            WHERE tok.token_address = %s
            ORDER BY t.timestamp DESC
            LIMIT 1;
        """
        rows = self.sql_helper.execute_select(sql, (token_mint,))
        return rows[0] if rows else None

    def get_open_trades(self, sim_mode: bool = False):
        sql = """
            SELECT 
                t.id,
                t.token_id,
                tok.token_address,
                t.trade_type,
                t.entry_usd,
                t.timestamp,
                t.simulation
            FROM trades t
            JOIN tokens tok ON t.token_id = tok.id
            WHERE t.status IN ('FINALIZED', 'SELLING', 'SIMULATED', 'RECOVERED')
            AND t.simulation = %s;
        """
        return self.sql_helper.execute_select(sql, (sim_mode,))

    def update_trade_status(self, trade_id: int, status: str):
        sql = """
            UPDATE trades
            SET status = %s
            WHERE id = %s;
        """
        params = (status,trade_id)
        self.sql_helper.execute_update(sql, params)

    def update_exit_data(self, trade_id: int, trigger_reason: str):
        sql = """
            UPDATE trades
            SET trigger_reason = %s
            WHERE id = %s;
        """
        self.sql_helper.execute_update(sql, (trigger_reason, trade_id))

    def close_trade(self, trade_id, exit_usd, pnl_percent, trigger_reason):
        sql = """
            UPDATE trades
            SET exit_usd = %s,
                pnl_percent = %s,
                trigger_reason = %s,
                status = 'CLOSED',
                finalized_at = NOW() AT TIME ZONE 'UTC'
            WHERE id = %s;
        """
        return self.sql_helper.execute_update(sql, (exit_usd, pnl_percent, trigger_reason, trade_id))

    def get_trade_by_id(self, trade_id: int):
        sql = "SELECT * FROM trades WHERE id = %s"
        rows = self.sql_helper.execute_select(sql, (trade_id,))
        return rows[0] if rows else None
    
    def get_live_trades(self, sim_mode: bool = False):
        sql = """
            SELECT 
                t.id,
                t.token_id,
                tok.token_address,
                t.trade_type,
                t.entry_usd,
                t.timestamp,
                t.simulation,
                t.status
            FROM trades t
            JOIN tokens tok ON t.token_id = tok.id
            WHERE t.status IN ('FINALIZED', 'SELLING', 'SIMULATED')
            AND t.simulation = %s;
        """
        return self.sql_helper.execute_select(sql, (sim_mode,))
