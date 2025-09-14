import os
import json
from datetime import datetime
from helpers.logging_manager import LoggingHandler


logger = LoggingHandler.get_logger()


def convert_blocktime_to_readable_format(blocktime):
    readble_fomrat = datetime.fromtimestamp(blocktime).strftime('%H:%M:%S')
    return readble_fomrat

def get_the_dif_between_unix_timestamps(current_time, unix_timestamp):
    return current_time - unix_timestamp
    
def get_payload(file) -> json:
    path = os.path.join(os.path.dirname(__file__), "..", "data", f"{file}.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def validate_bot_settings(settings):
    # Core numbers
    if not isinstance(settings["MIN_TOKEN_LIQUIDITY"], (int, float)):
        raise TypeError("MIN_TOKEN_LIQUIDITY must be a number")

    if not isinstance(settings["MAX_TOKEN_AGE_SECONDS"], int):
        raise TypeError("MAX_TOKEN_AGE_SECONDS must be an integer")

    if not isinstance(settings["TRADE_AMOUNT"], (int, float)):
        raise TypeError("TRADE_AMOUNT must be a number")

    if not isinstance(settings["MAXIMUM_TRADES"], int):
        raise TypeError("MAXIMUM_TRADES must be an integer")

    if not isinstance(settings["SIM_MODE"], bool):
        raise TypeError("SIM_MODE must be a bool")

    # Trading thresholds
    for key in ["TP", "SL", "TRAILING_STOP", "MIN_TSL_TRIGGER_MULTIPLIER", "TIMEOUT_PROFIT_THRESHOLD"]:
        if not isinstance(settings[key], (int, float)):
            raise TypeError(f"{key} must be a number (int or float)")

    if not isinstance(settings["TIMEOUT_SECONDS"], int):
        raise TypeError("TIMEOUT_SECONDS must be an integer")

    # Exit rules
    exit_rules = settings.get("EXIT_RULES", {})
    if not isinstance(exit_rules, dict):
        raise TypeError("EXIT_RULES must be a dict")
    for k, v in exit_rules.items():
        if not isinstance(v, bool):
            raise TypeError(f"EXIT_RULES.{k} must be a bool")

    # Notification settings
    notify = settings.get("NOTIFY", {})
    if not isinstance(notify, dict):
        raise TypeError("NOTIFY must be a dict")
    for key in ["DISCORD", "TELEGRAM", "SLACK"]:
        if not isinstance(notify.get(key, False), bool):
            raise TypeError(f"NOTIFY.{key} must be a bool")
    for key in ["DISCORD_WEBHOOK", "TELEGRAM_CHAT_ID", "SLACK_WEBHOOK"]:
        if not isinstance(notify.get(key, ""), str):
            raise TypeError(f"NOTIFY.{key} must be a string")

    # API rate limits
    rl = settings.get("RATE_LIMITS", {})
    for api in ["helius", "jupiter"]:
        if api not in rl:
            raise ValueError(f"Missing RATE_LIMITS config for: {api}")
        if not isinstance(rl[api].get("min_interval"), (int, float)):
            raise TypeError(f"{api} min_interval must be a number")
        jitter = rl[api].get("jitter_range")
        if not (isinstance(jitter, tuple) and len(jitter) == 2 and all(isinstance(j, (int, float)) for j in jitter)):
            raise TypeError(f"{api} jitter_range must be a tuple of 2 numbers")

    logger.info("✅ BOT_SETTINGS validation passed")
    return True






