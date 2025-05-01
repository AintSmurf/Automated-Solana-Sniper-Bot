import asyncio
from discord_bot.bot import Discord_Bot
from connectors.helius_connector import HeliusConnector
from helpers.logging_manager import LoggingHandler
from helpers.solana_manager import SolanaHandler
import threading
import time
from helpers.open_positions import OpenPositionTracker
from helpers.open_positions import OpenPositionTracker
from utilities.rug_check_utility import RugCheckUtility

# set up logger
logger = LoggingHandler.get_logger()


def start_discord_bot():
    ds = Discord_Bot()
    asyncio.run(ds.run())


def main():
    helius_connector = HeliusConnector()
    tracker = OpenPositionTracker(1.2, 0.95)

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


def test():
    sl = SolanaHandler()
    tracker = OpenPositionTracker()
    rug = RugCheckUtility()

    rug.is_liquidity_unlocked("")


if __name__ == "__main__":
    main()
    # test()
