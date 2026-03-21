import signal
import sys


class ShutdownManager:
    def __init__(self, app, logger):
        self.app = app
        self.logger = logger
        self._shutdown_started = False

    def register_signals(self):
        signal.signal(signal.SIGINT, self._handle_signal)

        if hasattr(signal, "SIGTERM"):
            signal.signal(signal.SIGTERM, self._handle_signal)

    def _handle_signal(self, signum, frame):
        if signum == signal.SIGINT:
            reason = "SIGINT"
        elif hasattr(signal, "SIGTERM") and signum == signal.SIGTERM:
            reason = "SIGTERM"
        else:
            reason = f"SIGNAL_{signum}"

        self.shutdown(reason=reason, mark_paused=True, exit_code=0)

    def shutdown(self, reason: str, mark_paused: bool = True, exit_code: int = 0):
        if self._shutdown_started:
            return

        self._shutdown_started = True

        self.logger.info(
            f"🛑 {reason} received, shutting down gracefully..."
        )

        orchestrator = getattr(self.app, "orchestrator", None)

        if orchestrator:
            if mark_paused:
                try:
                    orchestrator.ctx.get("run_session_manager").mark_paused(reason=reason)
                except Exception as e:
                    self.logger.warning(
                        f"⚠️ Failed to mark run as PAUSED: {e}",
                        exc_info=True
                    )

            orchestrator.shutdown()

        sys.exit(exit_code)