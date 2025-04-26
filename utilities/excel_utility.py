import os
import pandas as pd
from helpers.logging_manager import LoggingHandler

# set up logger
logger = LoggingHandler.get_logger()


class ExcelUtility:
    def __init__(self):
        self.base_dir = os.path.abspath("results")
        self.bought_tokens_dir = os.path.abspath("tokens_to_track")
        self.TOKENS_DIR = os.path.join(self.base_dir, "tokens")
        self.BOUGHT_TOKENS = os.path.join(self.bought_tokens_dir, "bought_tokens")
        self.create_folders()

    def create_folders(self):
        os.makedirs(self.BOUGHT_TOKENS, exist_ok=True)
        os.makedirs(self.TOKENS_DIR, exist_ok=True)
        logger.info("✅ Successfully created folders ..")

    def save_to_csv(self, directory, filename, data):
        filepath = os.path.join(directory, filename)
        df = pd.DataFrame(data)

        if os.path.exists(filepath):
            existing_df = pd.read_csv(filepath)
            updated_df = pd.concat([existing_df, df], ignore_index=True)
        else:
            updated_df = df

        updated_df.to_csv(filepath, index=False)
        logger.debug(f"✅ Data saved to {filepath}")
