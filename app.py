import threading
import time
import asyncio
from discord_bot.bot import Discord_Bot
from connectors.helius_connector import HeliusConnector
from helpers.logging_handler import LoggingHandler
from utilities.rug_check_utility import RugCheckUtility
from helpers.solana_handler import SolanaHandler

# set up logger
logger = LoggingHandler.get_logger()


def start_discord_bot():
    """Runs the Discord bot in an event loop."""
    ds = Discord_Bot()
    asyncio.run(ds.run())


def main():
    # Initialize HeliusConnector
    helius_connector = HeliusConnector()

    # Start WebSocket in a separate thread
    ws_thread = threading.Thread(target=helius_connector.start_ws, daemon=True)
    ws_thread.start()
    logger.info("🚀 WebSocket Started")

    # Start transaction fetcher in a separate thread
    fetcher_thread = threading.Thread(
        target=helius_connector.run_transaction_fetcher, daemon=True
    )
    fetcher_thread.start()
    logger.info("✅ Transaction fetcher started")

    # Start Discord bot + Excel watcher in a separate thread
    discord_thread = threading.Thread(target=start_discord_bot, daemon=True)
    discord_thread.start()
    logger.info("✅ Discord bot (with Excel watcher) started in a separate thread")

    # Keep script running
    while True:
        time.sleep(1)


def test():
    # rg = RugCheckUtility()
    # print(rg.is_liquidity_unlocked("CCYBBVkocwTk85qT4jbb8k65u2ufYkjoyrdFkUPKGVs6"))
    sl = SolanaHandler()
    # print(sl.get_account_balances())
    # sl.add_token_account("GbNL8c7t2RjRRvTtN4ZSAFswvp1K3gf7GoBnaK9sgxqH")
    token_handler = TokenHandler()
    print(sl.get_sol_price())
    # # print(test)
    # quote = token_handler.get_quote(
    #     "4yV5oPzVdXgJeWksWX2NgHRnn4yDbXhgmbEuaCQFpump",
    #     "So11111111111111111111111111111111111111112",
    #     1000,
    # )
    # ts = token_handler.get_swap_transaction(quote)
    # print(token_handler.simulate_transaction(ts))


if __name__ == "__main__":
    main()
    # test()
