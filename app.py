import asyncio
from discord_bot.bot import Discord_Bot
from connectors.helius_connector import HeliusConnector
from helpers.logging_manager import LoggingHandler
from helpers.solana_manager import SolanaHandler
from utilities.rug_check_utility import RugCheckUtility
import threading
import time

# set up logger
logger = LoggingHandler.get_logger()


def start_discord_bot():
    ds = Discord_Bot()
    asyncio.run(ds.run())


def main():
    helius_connector = HeliusConnector()

    ws_thread = threading.Thread(target=helius_connector.start_ws, daemon=True)
    ws_thread.start()
    logger.info("🚀 WebSocket Started")

    fetcher_thread = threading.Thread(
        target=helius_connector.run_transaction_fetcher, daemon=True
    )
    fetcher_thread.start()
    logger.info("✅ Transaction fetcher started")

    discord_thread = threading.Thread(target=start_discord_bot, daemon=True)
    discord_thread.start()
    logger.info("✅ Discord bot (with Excel watcher) started in a separate thread")

    while True:
        time.sleep(1)


if __name__ == "__main__":
    main()
