# notification/manager.py
import asyncio
import threading
from helpers.logging_manager import LoggingHandler
from notification.discord_bot import Discord_Bot  # add Slack_Bot/Telegram_Bot later

logger = LoggingHandler.get_logger()


class NotificationManager:
    """
    Runs all async notifiers (Discord/Slack/Telegram) inside ONE dedicated asyncio
    event loop thread. Core trading stays threaded; notifications stay async
    but isolated from the rest of the app.
    """
    def __init__(self, settings):
        self.settings = settings
        self.notifiers = []
        self.loop: asyncio.AbstractEventLoop | None = None
        self.thread: threading.Thread | None = None

        # ---- Register notifiers from settings ----
        notify_cfg = settings.get("NOTIFY", {})

        if notify_cfg.get("DISCORD", False):
            self.notifiers.append(Discord_Bot())
            logger.info("💬 Discord notifications enabled")

        # Future:
        # if notify_cfg.get("SLACK", False):
        #     self.notifiers.append(Slack_Bot(settings))

        # if notify_cfg.get("TELEGRAM", False):
        #     self.notifiers.append(Telegram_Bot(settings))
    # ---------------- Lifecycle ----------------
    def start(self):
        """
        Start a dedicated thread + asyncio loop. Each notifier gets its `run()` coroutine
        scheduled on that loop. The loop runs forever until `shutdown()` is called.
        """
        if self.thread is not None:
            logger.warning("⚠️ NotificationManager.start() called twice; ignoring.")
            return

        def runner():
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)

            # Schedule all notifiers' run() coroutines
            for n in self.notifiers:
                self.loop.create_task(n.run())

            logger.info("💬 Notification loop running")
            try:
                self.loop.run_forever()
            finally:
                # Close loop after stop
                pending = asyncio.all_tasks(self.loop)
                for t in pending:
                    t.cancel()
                try:
                    self.loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                except Exception:
                    pass
                self.loop.close()
                logger.info("🛑 Notification loop closed")

        self.thread = threading.Thread(target=runner, daemon=True, name="NotifierLoopThread")
        self.thread.start()
        logger.info("💬 Notification manager started")

    def shutdown(self):
        """
        Stop all notifiers and tear down the loop thread.
        This method is SYNC: it dispatches coroutine shutdowns onto the notifier loop
        and waits for them to complete.
        """
        if not self.notifiers or not self.loop or not self.thread:
            logger.info("ℹ️ No notifiers/loop to stop")
            return

        # Run each notifier's shutdown() INSIDE the notifier loop
        for n in self.notifiers:
            try:
                fut = asyncio.run_coroutine_threadsafe(n.shutdown(), self.loop)
                fut.result(timeout=10)
            except Exception as e:
                logger.warning(f"⚠️ Notifier shutdown failed: {e}")

        # Stop the loop and wait for the thread to finish
        try:
            self.loop.call_soon_threadsafe(self.loop.stop)
        except Exception:
            pass

        self.thread.join(timeout=10)
        logger.info("🛑 All notifiers stopped")
    # ---------------- Sending API ----------------
    def notify_text(self, message: str, channel_hint: str | None = None):
        """
        Simple unified text notification. For Discord we use a channel name hint
        (defaults to 'solana_tokens' if None).
        """
        if not self.loop:
            logger.warning("⚠️ Notification loop not running; cannot send message.")
            return

        # Discord
        for n in self.notifiers:
            if hasattr(n, "send_message_to_discord"):
                ch = channel_hint or "solana_tokens"
                try:
                    fut = asyncio.run_coroutine_threadsafe(
                        n.send_message_to_discord(ch, message),
                        self.loop
                    )
                    fut.result(timeout=5)
                except Exception as e:
                    logger.warning(f"⚠️ Failed to send Discord message: {e}")
