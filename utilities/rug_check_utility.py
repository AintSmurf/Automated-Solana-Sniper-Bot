from config.urls import RUGCHECK
from utilities.requests_utility import RequestsUtility
from helpers.logging_handler import LoggingHandler
from pprint import pprint

# set up logger
logger = LoggingHandler.get_logger()


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
        return data["score"] <= 3000

    def is_liquidity_unlocked(self, token_address):
        """
        Checks if a token's liquidity is unlocked or at risk of being unlocked soon.
        """
        logger.info(f"🔍 Checking token liquidity for {token_address} ...")
        url = self.token_risk + f"/{token_address}/report/summary"
        data = self.requests_utility.get(url)

        for risk in data.get("risks", []):
            risk_name = risk.get("name", "")
            risk_description = risk.get("description", "")

            logger.debug(f"🛠️ Risk found: {risk}")
            if (
                "LP Unlocked" in risk_name
                or "LP tokens are unlocked" in risk_description
            ):
                logger.warning(
                    f"🚨 Token {token_address} has UNLOCKED liquidity! (Rug Pull Risk)"
                )
                return True

            if "LP Unlock in" in risk_name and "will unlock soon" in risk_description:
                logger.warning(
                    f"⚠️ Token {token_address} liquidity will UNLOCK SOON! (High Rug Pull Risk)"
                )
                return True
        logger.info(f"✅ Token {token_address} has locked liquidity (Safe).")
        return False
