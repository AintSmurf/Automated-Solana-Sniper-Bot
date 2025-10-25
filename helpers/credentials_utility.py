import os
from helpers.logging_manager import LoggingHandler


# set up logger
logger = LoggingHandler.get_logger()


class CredentialsUtility:
    
    def get_helius_api_key(self):
        logger.info("retrieving helius api key ...")
        return os.environ["HELIUS_API_KEY"]

    def get_solana_private_wallet_key(self):
        logger.info("retrieving solana private key ...")
        return os.environ["SOLANA_PRIVATE_KEY"]

    def get_discord_token(self):
        logger.info("retrieving discord token ...")
        return os.environ["DISCORD_TOKEN"]

    def get_bird_eye_key(self):
        logger.info("retrieving Birdeye key ...")
        return os.environ["BIRD_EYE"]

    def get_dex(self):
        logger.info("retrieving DEX Name ...")
        return os.environ["DEX"]

    def get_db_creds(self):
        logger.info("retrieving Db creds ...")
        return{
            "DB_NAME":os.environ["DB_NAME"],
            "DB_HOST":os.environ["DB_HOST"],
            "DB_PORT":os.environ["DB_PORT"],
            "DB_USER":os.environ["DB_USER"],
            "DB_PASSWORD":os.environ["DB_PASSWORD"],
        }
    def get_all(self):
        return {
            "helius": self.get_helius_api_key(),
            "dex": self.get_dex(),
            "wallet_key": self.get_solana_private_wallet_key(),
            "bird_eye": self.get_bird_eye_key(),
            "discord": self.get_discord_token(),
            "db":self.get_db_creds()
        }
