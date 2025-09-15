import time
from config.settings import load_settings, prompt_bot_settings, prompt_ui_mode
from helpers.framework_manager import validate_bot_settings
from helpers.logging_manager import LoggingHandler
from interface.sniper_bot_ui import SniperBotUI
from helpers.bot_orchestrator import BotOrchestrator
from helpers.trade_counter import TradeCounter
import tkinter as tk


logger = LoggingHandler.get_logger()


def prepare_settings(headless=False):
    """Load settings, optionally run UI/CLI prompts, and validate."""
    settings = load_settings()
    if headless:
        settings["UI_MODE"] = False
        validate_bot_settings(settings)
        return settings

    prompt_ui_mode(settings)
    settings = load_settings()

    if not settings["UI_MODE"]:
        prompt_bot_settings(settings)
        settings = load_settings()

    validate_bot_settings(settings)
    return settings

def handle_ui_mode():
    app = SniperBotUI()
    app.mainloop()
    return True

def run_bot(settings):
    """Start the bot orchestrator in CLI or server mode."""
    trade_counter = TradeCounter(settings["MAXIMUM_TRADES"])
    orchestrator = BotOrchestrator(trade_counter, settings)
    try:
        orchestrator.start()
        orchestrator.run_cli_loop()
    finally:
        orchestrator.shutdown()
    
