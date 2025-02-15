from requests import get
from config.urls import DEXSCANNER
from utilities.requests_utility import RequestsUtility


class Dexscanner_utility:
    def __init__(self):
        self.requests_utility = RequestsUtility()
        self.new_pairs = DEXSCANNER["NEW_TOKENS"]
        self.data = DEXSCANNER["TOKEN_DATA"]

    def print_solana_tokens(self):
        data = self.requests_utility.get(self.new_pairs)
        solana_tokens = [token for token in data if token["chainId"] == "solana"]

        for token in solana_tokens:
            print(f"Token: {token.get('description', 'No description')}")
            print(f"Address: {token['tokenAddress']}")
            print(f"DEX Link: {token['url']}\n")
