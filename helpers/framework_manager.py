import os
import json
from config.bot_settings import BOT_SETTINGS

TRADE_COUNT_FILE = "trade_count.json"

def convert_date_to_readable_format():
    pass


def get_payload(file) -> json:
    path = os.path.join(os.path.dirname(__file__), "..", "data", f"{file}.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def validate_bot_settings():

    if not isinstance(BOT_SETTINGS["MIN_TOKEN_LIQUIDITY"], (int, float)):
        raise TypeError("MIN_TOKEN_LIQUIDITY must be a number")

    if not isinstance(BOT_SETTINGS["MAX_TOKEN_AGE_SECONDS"], int):
        raise TypeError("MAX_TOKEN_AGE_SECONDS must be an integer")

    if not isinstance(BOT_SETTINGS["TRADE_AMOUNT"], (int, float)):
        raise TypeError("TRADE_AMOUNT must be a number")

    if not isinstance(BOT_SETTINGS["TP"], float):
        raise TypeError("TP must be a float")

    if not isinstance(BOT_SETTINGS["SL"], float):
        raise TypeError("SL must be a float")

    rl = BOT_SETTINGS.get("RATE_LIMITS", {})
    for api in ["helius", "JUPITER"]:
        if api not in rl:
            raise ValueError(f"Missing RATE_LIMITS config for: {api}")
        if not isinstance(rl[api].get("min_interval"), float):
            raise TypeError(f"{api} min_interval must be a float")
        jitter = rl[api].get("jitter_range")
        if not (isinstance(jitter, tuple) and len(jitter) == 2 and all(isinstance(j, float) for j in jitter)):
            raise TypeError(f"{api} jitter_range must be a tuple of 2 floats")

    return True


def load_trade_count():
    if os.path.exists(TRADE_COUNT_FILE):
        with open(TRADE_COUNT_FILE, "r") as f:
            return json.load(f).get("count", 0)
    return 0

def save_trade_count(count):
    with open(TRADE_COUNT_FILE, "w") as f:
        json.dump({"count": count}, f)

