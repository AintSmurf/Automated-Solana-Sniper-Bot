import os
import logging as logger


class CredentialsUtility:
    def __init__(self) -> None:
        self.api_key = ""
        self.secret_key = ""

    def get_helius_api_key(self):
        logger.info("retriving helius api key ...")
        self.api_key = os.environ["API_KEY"]
        return {"API_KEY": self.api_key}
