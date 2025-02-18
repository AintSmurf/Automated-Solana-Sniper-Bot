from config.urls import RUGCHECK
from utilities.requests_utility import RequestsUtility
import logging as logger


class RugCheckUtility:
    def __init__(self):
        base_url = RUGCHECK["BASE_URL"]
        self.token_risk = RUGCHECK["TOKEN_RISK"]
        self.requests_utility = RequestsUtility(base_url)
        logger.info("initialized Rugcheck class.")

    def check_token_security(self, token_address):
        logger.info("checking token security ...")
        url = self.token_risk + f"/{token_address}/report/summary"
        data = self.requests_utility.get(url)
        print(data)
