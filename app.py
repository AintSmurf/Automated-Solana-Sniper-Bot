from pprint import pprint
from utilities.dexscanner_utility import Dexscanner_utility
import logging as logger

logger.basicConfig(level=logger.INFO)


def main():
    dexscanner_utility = Dexscanner_utility()
    dexscanner_utility.print_solana_tokens()
    dexscanner_utility.get_token_pair_address(
        "solana", "2YjiMehvYgKpKdVNpkZHcdtd8L2FJhBHRZ2rT7mcmoon"
    )
    # dexscanner_utility.get_token_data(
    #     "solana",
    #     "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",
    # )


if __name__ == "__main__":
    main()
