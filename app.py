from pprint import pprint
from utilities.dexscanner_utility import DexscannerUtility
from utilities.rug_check_utility import RequestsUtility
from connectors.helius_connector import HeliusConnector
from helpers.logging_handler import LoggingHandler
from helpers.token_handler import TokenHandler
import time
import threading

logger_utility = LoggingHandler()
logger = logger_utility.get_logger()


def test():
    # helius_connector = HeliusConnector()
    token_handler = TokenHandler()
    is_honeypot = token_handler.is_honeypot(
        "H1pqkHGyaHube3HRBJhZ4zWw8SRTXa5nDZ22bRYz2QuJ", 10000
    )
    if is_honeypot:
        print("🚨 Token is a honeypot!")
    else:
        print("✅ Token is tradable!")


def main():

    logger.info("🚀 Application Started")
    # Initialize the HeliusConnector instance
    helius_connector = HeliusConnector()

    # Start WebSocket in a separate thread
    ws_thread = threading.Thread(target=helius_connector.start_ws, daemon=True)
    ws_thread.start()

    # Start transaction fetcher in a separate thread
    fetcher_thread = threading.Thread(
        target=helius_connector.run_transaction_fetcher, daemon=True
    )
    fetcher_thread.start()

    # Keep script running
    while True:
        time.sleep(1)


if __name__ == "__main__":
    main()
    # test()
