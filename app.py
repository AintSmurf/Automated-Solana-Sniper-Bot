from pprint import pprint
from utilities.dexscanner_utility import Dexscanner_utility


def main():
    dexscanner_utility = Dexscanner_utility()
    dexscanner_utility.get_solana_tokens()


if __name__ == "__main__":
    main()
