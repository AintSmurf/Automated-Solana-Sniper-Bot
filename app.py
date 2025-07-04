import asyncio
from discord_bot.bot import Discord_Bot
from connectors.helius_connector import HeliusConnector
from helpers.logging_manager import LoggingHandler
import threading
import time
from helpers.open_positions import OpenPositionTracker
from helpers.open_positions import OpenPositionTracker
from helpers.rate_limiter import RateLimiter

# set up logger
logger = LoggingHandler.get_logger()


def start_discord_bot():
    ds = Discord_Bot()
    asyncio.run(ds.run())

def main():
    
    shared_helius_limiter = RateLimiter(min_interval=0.1, jitter_range=(0.01, 0.02))
    helius_connector = HeliusConnector(rate_limiter=shared_helius_limiter)
    tracker = OpenPositionTracker(1.3, 0.85,shared_helius_limiter)


    ws_thread = threading.Thread(target=helius_connector.start_ws, daemon=True)
    ws_thread.start()
    logger.info("🚀 WebSocket Started")

    fetcher_thread = threading.Thread(
        target=helius_connector.run_transaction_fetcher, daemon=True
    )
    fetcher_thread.start()
    logger.info("✅ Transaction fetcher started")

    trakcer_thread = threading.Thread(target=tracker.track_positions, daemon=True)
    trakcer_thread.start()
    logger.info("✅ Position tracker started")

    discord_thread = threading.Thread(target=start_discord_bot, daemon=True)
    discord_thread.start()
    logger.info("✅ Discord bot (with Excel watcher) started in a separate thread")

    while True:
        time.sleep(1)


if __name__ == "__main__":
    main()
