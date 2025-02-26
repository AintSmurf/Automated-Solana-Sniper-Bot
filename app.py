import asyncio
from discord_bot.bot import Discord_Bot
from connectors.helius_connector import HeliusConnector
from helpers.logging_manager import LoggingHandler
from utilities.rug_check_utility import RugCheckUtility
from helpers.solana_manager import SolanaHandler

# set up logger
logger = LoggingHandler.get_logger()


async def main():
    logger.info("🚀 Initializing components...")

    helius_connector = HeliusConnector()

    logger.info("🚀 WebSocket Starting...")
    logger.info("✅ Transaction fetcher starting...")
    logger.info("✅ Discord bot (with Excel watcher) starting...")

    await asyncio.gather(
        helius_connector.start_ws(),
        helius_connector.run_transaction_fetcher(),
        Discord_Bot().run(),
    )


def test():
    # rg = RugCheckUtility()
    # print(rg.is_liquidity_unlocked("CCYBBVkocwTk85qT4jbb8k65u2ufYkjoyrdFkUPKGVs6"))
    sl = SolanaHandler()
    sl.add_token_account("7BNwDrLsyiQmGN7PKMUPtVCRMetuG6b6xLRiAhdZpump")
    amount = sl.get_token_worth_in_usd(
        "7BNwDrLsyiQmGN7PKMUPtVCRMetuG6b6xLRiAhdZpump", 25
    )
    quote = sl.get_quote(
        "So11111111111111111111111111111111111111112",
        "7BNwDrLsyiQmGN7PKMUPtVCRMetuG6b6xLRiAhdZpump",
        amount,
    )
    txn64 = sl.get_swap_transaction(quote)
    print(sl.simulate_transaction(txn64))
    # sl.buy_token(
    #     "So11111111111111111111111111111111111111112",
    #     "AU8d6byi8tmFpB5Lg1uAKPoiJX2vPcCVovubhdocpump",
    #     25,
    # )


if __name__ == "__main__":
    # asyncio.run(main())
    test()
