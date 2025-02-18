from pprint import pprint
from utilities.dexscanner_utility import DexscannerUtility
from utilities.rug_check_utility import RequestsUtility
from connectors.helius_connector import HeliusConnector
import time
import logging as logger

logger.basicConfig(level=logger.INFO)


def main():
    helius_connector = HeliusConnector(devnet=False)
    while True:
        time.sleep(1)

    # dexscanner_utility = DexscannerUtility()
    # rug_Check_Utility = RequestsUtility()
    # dexscanner_utility.print_solana_tokens()
    # rug_Check_Utility.check_token_security(
    #     "CUDQ4vyucEyY3TpP3Mm2wDJ4BnGUGBNQtKMU1Smvpump"
    # )
    # dexscanner_utility.get_token_pair_address(
    #     "solana", "2YjiMehvYgKpKdVNpkZHcdtd8L2FJhBHRZ2rT7mcmoon"
    # )
    # dexscanner_utility.get_token_data(
    #     "solana",
    #     "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",
    # )


if __name__ == "__main__":
    main()
