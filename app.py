import asyncio
from discord_bot.bot import Discord_Bot
from connectors.helius_connector import HeliusConnector
from helpers.logging_manager import LoggingHandler
from helpers.solana_manager import SolanaHandler
from connectors.liquidity_connector import DataManager

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
    # pass
    # helius_connector = HeliusConnector()
    solana_manager = SolanaHandler()
    print(
        solana_manager.get_raydium_marketcap(
            "53pKGZ9JAvkpMEmfdhm3epX9bVRjLJaBGjSgHAWipump"
        )
    )
    print(
        solana_manager.get_raydium_liquidity(
            "53pKGZ9JAvkpMEmfdhm3epX9bVRjLJaBGjSgHAWipump"
        )
    )
    # print(
    #     helius_connector.get_raydium_liquidity(
    #         "53pKGZ9JAvkpMEmfdhm3epX9bVRjLJaBGjSgHAWipump"
    #     )
    # )
    # print(
    #     helius_connector.get_raydium_marketcap(
    #         "53pKGZ9JAvkpMEmfdhm3epX9bVRjLJaBGjSgHAWipump"
    #     )
    # )

    # rg = RugCheckUtility()
    # print(rg.is_liquidity_unlocked("CCYBBVkocwTk85qT4jbb8k65u2ufYkjoyrdFkUPKGVs6"))
    # sl = SolanaHandler()
    # sl.add_token_account("AvNXHBAk9wSQWeVPzTTYJp5VCpnW73fBdp7ijbyrpump")
    # amount = sl.get_token_worth_in_usd(
    #     "AvNXHBAk9wSQWeVPzTTYJp5VCpnW73fBdp7ijbyrpump", 25
    # )
    # quote = sl.get_quote(
    #     "So11111111111111111111111111111111111111112",
    #     "AvNXHBAk9wSQWeVPzTTYJp5VCpnW73fBdp7ijbyrpump",
    #     amount,
    # )
    # txn64 = sl.get_swap_transaction(quote)
    # print(sl.simulate_transaction(txn64))
    # sl.send_transaction(
    #     "So11111111111111111111111111111111111111112",
    #     "AvNXHBAk9wSQWeVPzTTYJp5VCpnW73fBdp7ijbyrpump",
    #     15,
    # )


if __name__ == "__main__":
    # asyncio.run(main())
    test()
