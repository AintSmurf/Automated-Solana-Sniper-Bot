from pprint import pprint
from utilities.dexscanner_utility import DexscannerUtility
from utilities.rug_check_utility import RequestsUtility
from connectors.helius_connector import HeliusConnector
import time
import logging as logger
import threading

logger.basicConfig(level=logger.INFO)


def main():
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
