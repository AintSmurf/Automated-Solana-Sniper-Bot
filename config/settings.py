import json
import os
import copy
from helpers.logging_manager import LoggingHandler

logger = LoggingHandler.get_logger()

DEFAULT_SETTINGS = {
    # bot settings
    "UI_MODE": False,
    "MIN_TOKEN_LIQUIDITY": 10000,
    "MAX_TOKEN_AGE_SECONDS": 30,
    "TRADE_AMOUNT": 10,
    "MAXIMUM_TRADES": 20,
    "SIM_MODE": True,
    "TIMEOUT_SECONDS": 45,
    "TIMEOUT_PROFIT_THRESHOLD": 1.03,

    # Trading logic thresholds
    "TP": 4.0,                              # Take profit multiplier
    "SL": 0.25,                             # Emergency SL threshold
    "TRAILING_STOP": 0.2,                   # TSL % drop from peak
    "MIN_TSL_TRIGGER_MULTIPLIER": 1.5,      # TSL only after 1.5x pump

    # ✅ Exit rule toggles
    "EXIT_RULES": {
        "USE_TP": False,
        "USE_TSL": False,
        "USE_SL": False,
        "USE_TIMEOUT": False
    },

    # ✅ Notification channels
    "NOTIFY": {
        "DISCORD": False,
        "DISCORD_WEBHOOK": "",
        "TELEGRAM": False,
        "TELEGRAM_CHAT_ID": "",
        "SLACK": False,
        "SLACK_WEBHOOK": ""
    },

    # API rate limits
    "RATE_LIMITS": {
        "helius": {
            "min_interval": 0.02,
            "jitter_range": [
                0.005,
                0.01
            ],
            "max_requests_per_minute": None,
            "name":"Helius_limits"
        },
        "jupiter": {
            "min_interval": 1.0,
            "jitter_range": [
                0.05,
                0.15
            ],
            "max_requests_per_minute": 60,
            "name":"Jupiter_limits"
        }
    }
}

SETTINGS_PATH = os.path.join(os.path.dirname(__file__), "bot_settings.json")


def load_settings():
    """Load settings file, merging with defaults and enforcing types."""
    if os.path.exists(SETTINGS_PATH):
        try:
            with open(SETTINGS_PATH, "r") as f:
                loaded = json.load(f)
                merged = merge_with_defaults(loaded, DEFAULT_SETTINGS)

                # normalize jitter ranges as tuples
                for api in ["helius", "jupiter"]:
                    jitter = merged["RATE_LIMITS"][api].get("jitter_range")
                    if jitter and len(jitter) == 2:
                        merged["RATE_LIMITS"][api]["jitter_range"] = tuple(jitter)

                return merged
        except Exception as e:
            logger.warning(f"⚠️ Failed to load settings file: {e}")

    # fallback: write fresh defaults
    defaults = copy.deepcopy(DEFAULT_SETTINGS)
    save_settings(defaults)
    logger.info("Created default bot_settings.json")
    return defaults

def save_settings(settings: dict):
    """Write settings to JSON (convert tuples to lists for JSON compatibility)."""
    serializable = copy.deepcopy(settings)

    # convert tuples to lists for JSON
    for api in ["helius", "jupiter"]:
        if "jitter_range" in serializable["RATE_LIMITS"][api]:
            jr = serializable["RATE_LIMITS"][api]["jitter_range"]
            serializable["RATE_LIMITS"][api]["jitter_range"] = list(jr)

    with open(SETTINGS_PATH, "w") as f:
        json.dump(serializable, f, indent=4)

def merge_with_defaults(user_settings, default_settings):
    """Recursive merge of user and default settings."""
    result = copy.deepcopy(default_settings)
    for key, val in user_settings.items():
        if isinstance(val, dict) and key in result:
            result[key] = merge_with_defaults(val, result[key])
        else:
            result[key] = val
    return result

def prompt_bot_settings(settings):
    print("\n🔧 Configure Sniper Bot Settings (press Enter to keep default):\n")

    def prompt_value(key, val):
        user_input = input(f"{key} [{val}]: ").strip()
        if not user_input:
            return val
        try:
            if isinstance(val, bool):
                return user_input.lower() in ("true", "1", "yes", "on")
            elif isinstance(val, int):
                return int(user_input)
            elif isinstance(val, float):
                return float(user_input)
            elif isinstance(val, (list, tuple)) and len(val) == 2:
                parts = user_input.split(",")
                if len(parts) == 2:
                    return [float(parts[0]), float(parts[1])]
                else:
                    raise ValueError("Invalid list format")
            else:
                return user_input
        except Exception:
            logger.error(f"❌ Invalid input for {key}, keeping default.")
            return val

    for key in settings:
        if key == "UI_MODE":
            continue
        if isinstance(settings[key], dict):
            print(f"\n📦 {key} Settings:")
            for sub_key in settings[key]:
                if isinstance(settings[key][sub_key], dict):
                    print(f"  🔹 {sub_key} Settings:")
                    for rate_key, rate_val in settings[key][sub_key].items():
                        full_key = f"{sub_key}.{rate_key}"
                        settings[key][sub_key][rate_key] = prompt_value(full_key, rate_val)
                else:
                    full_key = f"{key}.{sub_key}"
                    settings[key][sub_key] = prompt_value(full_key, settings[key][sub_key])
        else:
            settings[key] = prompt_value(key, settings[key])

    save_settings(settings)
    logger.info("✅ Settings saved to bot_settings.json\n")

def get_bot_settings():
    return load_settings()

def prompt_ui_mode(settings):
    default_ui = settings.get("UI_MODE", False)
    user_input = input(f"Would you like to launch the bot with a graphical interface? (y/n) [{default_ui}]: ").strip().lower()

    if user_input in ("yes", "y", "true", "1"):
        settings["UI_MODE"] = True
    elif user_input in ("no", "n", "false", "0"):
        settings["UI_MODE"] = False
    else:
        logger.warning(f"⚠️ Invalid input for UI_MODE, keeping [{default_ui}]")
        settings["UI_MODE"] = default_ui

    save_settings(settings)
    return settings["UI_MODE"]
