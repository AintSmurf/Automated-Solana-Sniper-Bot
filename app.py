import asyncio
from discord_bot.bot import Discord_Bot
from connectors.helius_connector import HeliusConnector
from helpers.logging_manager import LoggingHandler
import threading
import time
from helpers.open_positions import OpenPositionTracker
from helpers.rate_limiter import RateLimiter
from config.bot_settings import BOT_SETTINGS
from helpers.framework_manager import validate_bot_settings

# set up logger
logger = LoggingHandler.get_logger()


def start_discord_bot():
    ds = Discord_Bot()
    asyncio.run(ds.run())

def main():
    # Use shared rate limiter from config
    helius_rl_settings = BOT_SETTINGS["RATE_LIMITS"]["helius"]
    shared_helius_limiter = RateLimiter(
        min_interval=helius_rl_settings["min_interval"],
        jitter_range=helius_rl_settings["jitter_range"]
    )

    # Init components with config values
    helius_connector = HeliusConnector(rate_limiter=shared_helius_limiter)

    tracker = OpenPositionTracker(
        tp=BOT_SETTINGS["TP"],
        sl=BOT_SETTINGS["SL"],
        rate_limiter=shared_helius_limiter
    )

    # Launch threads
    threading.Thread(target=helius_connector.start_ws, daemon=True).start()
    logger.info("🚀 WebSocket Started")

    threading.Thread(target=helius_connector.run_transaction_fetcher, daemon=True).start()
    logger.info("✅ Transaction fetcher started")

    threading.Thread(target=tracker.track_positions, daemon=True).start()
    logger.info("✅ Position tracker started")

    threading.Thread(target=start_discord_bot, daemon=True).start()
    logger.info("✅ Discord bot (with Excel watcher) started in a separate thread")

    # Keep main thread alive
    while True:
        time.sleep(1)

if __name__ == "__main__":
    try:
        validate_bot_settings()
        main()
    except Exception as e:
        logger.error(f"❌ BOT_SETTINGS validation failed: {e}")
        exit(1)
