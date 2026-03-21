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
                tr.trade_time         AS entry_time,
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
            AND tr.trade_time >= %s
            AND tr.trade_time < %s
            ORDER BY tr.trade_time;
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
            data_model_version=2,
            run_id=None
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
                    trade_time,
                    config_id,
                    safety_result_id,
                    volume_snapshot_id,
                    data_model_version,
                    run_id
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,%s,%s)
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
                data_model_version,
                run_id,
            )
            return self.sql_helper.execute_insert(sql, params)

    def get_trade_by_buy_signature(self, buy_signature: str):
        sql = """
            SELECT t.*, tok.token_address
            FROM signatures s
            JOIN trades t ON t.id = s.trade_id
            JOIN tokens tok ON tok.id = t.token_id
            WHERE s.buy_signature = %s
            AND t.status IN ('SUBMITTED','CONFIRMED','FINALIZED','SELLING')
            ORDER BY t.trade_time DESC
            LIMIT 1;
        """
        rows = self.sql_helper.execute_select(sql, (buy_signature,))
        if rows:
            return rows[0]
        fallback_sql = """
            SELECT t.*, tok.token_address
            FROM signatures s
            JOIN trades t ON t.token_id = s.token_id
            JOIN tokens tok ON tok.id = t.token_id
            WHERE s.buy_signature = %s
            AND t.status IN ('SUBMITTED','CONFIRMED','FINALIZED','SELLING')
            ORDER BY t.trade_time DESC
            LIMIT 1;
        """
        rows = self.sql_helper.execute_select(fallback_sql, (buy_signature,))
        return rows[0] if rows else None

    def get_trade_by_token(self, token_mint: str, only_open: bool = True):
        sql = """
            SELECT t.*
            FROM trades t
            JOIN tokens tok ON tok.id = t.token_id
            WHERE tok.token_address = %s
        """
        params = [token_mint]

        if only_open:
            sql += " AND t.status <> 'CLOSED'"

        sql += """
            ORDER BY t.trade_time DESC
            LIMIT 1;
        """

        rows = self.sql_helper.execute_select(sql, tuple(params))
        return rows[0] if rows else None

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
                closed_at = NOW() AT TIME ZONE 'UTC'
            WHERE id = %s
            AND status <> 'CLOSED';
        """
        return self.sql_helper.execute_update(sql, (exit_usd, pnl_percent, trigger_reason, trade_id))
    
    def get_trade_by_id(self, trade_id: int):
        sql = "SELECT * FROM trades WHERE id = %s"
        rows = self.sql_helper.execute_select(sql, (trade_id,))
        return rows[0] if rows else None
    
    def update_trade_status_with_ts(self, trade_id: int, status: str):
        now_utc = datetime.now(timezone.utc)

        if status.upper() == "CONFIRMED":
            sql = "UPDATE trades SET status=%s, confirmed_at=%s WHERE id=%s;"
            self.sql_helper.execute_update(sql, ("CONFIRMED", now_utc, trade_id))
            return

        if status.upper() == "FINALIZED":
            sql = "UPDATE trades SET status=%s, finalized_at=%s WHERE id=%s;"
            self.sql_helper.execute_update(sql, ("FINALIZED", now_utc, trade_id))
            return

        sql = "UPDATE trades SET status=%s WHERE id=%s;"
        self.sql_helper.execute_update(sql, (status.upper(), trade_id))
    
    def get_latest_trade_by_token_and_statuses(self, token_mint: str, statuses: tuple[str, ...]):
        placeholders = ",".join(["%s"] * len(statuses))
        sql = f"""
            SELECT t.*
            FROM trades t
            JOIN tokens tok ON tok.id = t.token_id
            WHERE tok.token_address = %s
            AND t.status IN ({placeholders})
            ORDER BY t.trade_time DESC
            LIMIT 1;
        """
        rows = self.sql_helper.execute_select(sql, (token_mint, *statuses))
        return rows[0] if rows else None
    
    def get_submitted_trades(self,sim_mode: bool):
       sql = """
           SELECT 
               t.id,
               t.token_id,
               tok.token_address,
               t.trade_type,
               t.entry_usd,
               t.trade_time,
               t.simulation,
               t.status
           FROM trades t
           JOIN tokens tok ON t.token_id = tok.id
           WHERE t.simulation = %s
           AND t.status IN ('SUBMITTED','CONFIRMED');
       """
       return self.sql_helper.execute_select(sql, (sim_mode,))
    
    def get_live_trades(self,sim_mode: bool):
            sql = """
            SELECT 
                t.id,
                t.token_id,
                tok.token_address,
                t.trade_type,
                t.entry_usd,
                t.trade_time,
                t.simulation,
                t.status
            FROM trades t
            JOIN tokens tok ON t.token_id = tok.id
            WHERE t.simulation = %s
            AND t.status IN ('FINALIZED','RECOVERED','SIMULATED','EXIT_REQUESTED');
            """
            return self.sql_helper.execute_select(sql, (sim_mode,))
    
    def get_selling_trades(self,sim_mode: bool):
            sql = """
            SELECT 
                t.id,
                t.token_id,
                tok.token_address,
                t.trade_type,
                t.entry_usd,
                t.trade_time,
                t.simulation,
                t.status
            FROM trades t
            JOIN tokens tok ON t.token_id = tok.id
            WHERE t.simulation = %s
            AND t.status IN ('SELLING');
            """
            return self.sql_helper.execute_select(sql, (sim_mode,))
    
    def get_latest_trade_by_token_any_status(self, token_mint: str):
        sql = """
            SELECT t.*, tok.token_address
            FROM trades t
            JOIN tokens tok ON tok.id = t.token_id
            WHERE tok.token_address = %s
            ORDER BY t.trade_time DESC
            LIMIT 1;
        """
        rows = self.sql_helper.execute_select(sql, (token_mint,))
        return rows[0] if rows else None

    def reopen_trade(self, trade_id: int, status: str = "FINALIZED"):
        sql = """
            UPDATE trades
            SET status=%s,
                exit_usd=NULL,
                pnl_percent=NULL,
                trigger_reason=NULL,
                finalized_at=NOW() AT TIME ZONE 'UTC'
            WHERE id=%s;
        """
        self.sql_helper.execute_update(sql, (status, trade_id))
    
    def update_results_ids(self,trade_id: int,safety_result_id: int | None = None,volume_snapshot_id: int | None = None,liquidity_snapshot_id: int | None = None,) -> None:
        updates = []
        params = []
        if safety_result_id is not None:
            updates.append("safety_result_id = %s")
            params.append(safety_result_id)

        if volume_snapshot_id is not None:
            updates.append("volume_snapshot_id = %s")
            params.append(volume_snapshot_id)

        if liquidity_snapshot_id is not None:
            updates.append("liquidity_snapshot_id = %s")
            params.append(liquidity_snapshot_id)

        if not updates:
            return

        sql = f"""
            UPDATE trades
            SET {", ".join(updates)}
            WHERE id = %s;
        """
        params.append(trade_id)

        self.sql_helper.execute_update(sql, tuple(params))
         
    def count_trade_slots_used(self, run_id: int) -> int:
        sql = """
            SELECT COUNT(*)
            FROM trades
            WHERE run_id = %s
            AND status IN (
                'FINALIZED',
                'SELLING',
                'SIMULATED',
                'EXIT_REQUESTED',
                'SELL_TIMEOUT',
                'CLOSED'
            );
        """
        rows = self.sql_helper.execute_select(sql, (run_id,))
        return rows[0][0] if rows else 0