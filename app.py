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
from helpers.trade_counter import TradeCounter

# set up logger
logger = LoggingHandler.get_logger()


def start_discord_bot():
    ds = Discord_Bot()
    asyncio.run(ds.run())

def main():
    
    #Events to control shutdown
    stop_ws = threading.Event()
    stop_fetcher = threading.Event()
    stop_tracker = threading.Event()
    stop_retry = threading.Event()

    # Trade counter setup
    trade_counter = TradeCounter(BOT_SETTINGS["MAXIMUM_TRADES"])
    
    # Use shared rate limiter from config
    helius_rl_settings = BOT_SETTINGS["RATE_LIMITS"]["helius"]
    shared_helius_limiter = RateLimiter(
        min_interval=helius_rl_settings["min_interval"],
        jitter_range=helius_rl_settings["jitter_range"]
    )

    # Init components Helius
    helius_connector = HeliusConnector(
        rate_limiter=shared_helius_limiter,
        trade_counter=trade_counter,
        stop_ws=stop_ws,
        stop_fetcher=stop_fetcher
    )
    
    # Init components Tracker
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

    threading.Thread(target=tracker.track_positions, args=(stop_tracker,), daemon=True).start()
    logger.info("✅ Position tracker started")

    threading.Thread(target=tracker.retry_failed_sells, args=(stop_retry,), daemon=True).start()
    logger.info("🔄 Sell retry thread started")

    threading.Thread(target=start_discord_bot, daemon=True).start()
    logger.info("✅ Discord bot started")

    # Keep main thread alive
    while True:
        time.sleep(5)

        if trade_counter.reached_limit():
            # Stage 1: Stop trade-related threads
            if not stop_ws.is_set():
                logger.warning("🚫 MAXIMUM_TRADES reached — stopping trade threads.")
                stop_ws.set()
                stop_fetcher.set()

            # Stage 2: Stop tracker threads once work is done
            if not tracker.has_open_positions() and not tracker.has_failed_sells():
                logger.info("✅ All trades completed and positions cleared. Stopping all threads.")
                stop_tracker.set()
                stop_retry.set()
                break

    logger.info("🛑 Bot shutdown complete.")

if __name__ == "__main__":
    try:
        validate_bot_settings()
        main()
    except Exception as e:
        logger.error(f"❌ BOT_SETTINGS validation failed: {e}")
        exit(1)
