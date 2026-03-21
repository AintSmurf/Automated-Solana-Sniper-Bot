class RunSessionManager:
    def __init__(self, ctx):
        self.ctx = ctx
        self.logger = ctx.get("logger")
        self.run_session_dao = ctx.get("run_session_dao")

    def start_or_resume_run(self, config_id: int, run_label: str | None = None) -> int:
        existing = self.run_session_dao.get_latest_running_run(config_id)

        if existing:
            run_id = existing[0]
            self.logger.warning(
                f"♻️ Resuming existing RUNNING bot run: run_id={run_id}, config_id={config_id}"
            )
            return run_id

        run_id = self.run_session_dao.create_run(config_id=config_id, run_label=run_label)

        self.logger.info(
            f"🟢 Created new bot run: run_id={run_id}, config_id={config_id}, label={run_label}"
        )

        return run_id

    def mark_paused(self, reason: str = "manual_stop"):
        run_id = self.ctx.get("run_id")
        if run_id:
            self.run_session_dao.mark_status(run_id, "PAUSED", reason)
            self.logger.warning(f"⏸️ Marked run_id={run_id} as PAUSED. reason={reason}")

    def mark_clean_shutdown(self, reason: str = "clean_shutdown"):
        run_id = self.ctx.get("run_id")
        if run_id:
            self.run_session_dao.mark_status(run_id, "CLEAN_SHUTDOWN", reason)
            self.logger.info(f"✅ Marked run_id={run_id} as CLEAN_SHUTDOWN.")

    def mark_max_trades_done(self):
        run_id = self.ctx.get("run_id")
        if run_id:
            self.run_session_dao.mark_status(run_id, "MAX_TRADES_DONE", "max_trades_done")
            self.logger.info(f"🏁 Marked run_id={run_id} as MAX_TRADES_DONE.")