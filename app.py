from helpers.logging_manager import LoggingHandler
from helpers.bot_runner import prepare_settings, run_bot
import argparse
import sys
from helpers.bot_runner import handle_ui_mode

# set up logger
logger = LoggingHandler.get_logger()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--s", "--server", dest="server", action="store_true",
        help="Run in server mode (no CLI loop prompts)"
    )
    args = parser.parse_args()

    # Load settings (UI_MODE and other flags included)
    settings = prepare_settings(headless=args.server)

    if settings.get("UI_MODE", False):   
        handle_ui_mode()
    else:
        run_bot(settings)
    sys.exit(0)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("🛑 Ctrl+C received, shutting down gracefully...")
        sys.exit(0)
    except Exception as e:
        logger.error(f"❌ BOT_SETTINGS validation failed: {e}", exc_info=True)
        sys.exit(1)
