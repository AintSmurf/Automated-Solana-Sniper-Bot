class RunSessionDAO:
    VALID_STATUSES = {
        "RUNNING",
        "PAUSED",
        "CLEAN_SHUTDOWN",
        "MAX_TRADES_DONE",
        "FAILED",
        "ABANDONED",
    }

    FINAL_STATUSES = {
        "PAUSED",
        "CLEAN_SHUTDOWN",
        "MAX_TRADES_DONE",
        "FAILED",
        "ABANDONED",
    }

    def __init__(self, ctx):
        self.ctx = ctx
        self.db = ctx.get("sql_db")
        self.logger = ctx.get("logger")

    def create_run(self, config_id: int, run_label: str | None = None) -> int:
        query = """
            INSERT INTO bot_runs (config_id, run_label, status)
            VALUES (%s, %s, 'RUNNING')
            RETURNING id
        """
        return self.db.execute_insert(query, (config_id, run_label))

    def get_latest_running_run(self, config_id: int):
        query = """
            SELECT id, config_id, run_label, status, started_at
            FROM bot_runs
            WHERE config_id = %s
              AND status = 'RUNNING'
            ORDER BY started_at DESC
            LIMIT 1
        """
        rows = self.db.execute_select(query, (config_id,))
        return rows[0] if rows else None

    def mark_status(self, run_id: int, status: str, reason: str | None = None) -> int:
        if status not in self.VALID_STATUSES:
            raise ValueError(f"Invalid run status: {status}")

        should_end = status in self.FINAL_STATUSES

        query = """
            UPDATE bot_runs
            SET status = %s,
                shutdown_reason = %s,
                ended_at = CASE
                    WHEN %s THEN NOW()
                    ELSE ended_at
                END,
                updated_at = NOW()
            WHERE id = %s
        """
        return self.db.execute_update(query, (status, reason, should_end, run_id))