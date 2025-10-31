import argparse
from datetime import datetime ,timedelta
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
import subprocess
import os
from dao.token_dao import TokenDAO
from services.bot_context import BotContext
from helpers.credentials_utility import CredentialsUtility
from config.settings import Settings
from services.sql_db_utility import SqlDBUtility

EXTRACTOR_SCRIPT = os.path.join(os.path.dirname(__file__), "analyze.py")
MAX_WORKERS = 10


def build_context():
    credentials = CredentialsUtility()
    credentials_dict = credentials.get_all()

    settings_manager = Settings()
    first_run = settings_manager.is_first_run()
    bot_settings = settings_manager.load_settings()
    settings_manager.validate_bot_settings(bot_settings)

    ctx = BotContext(
        settings=bot_settings,
        api_keys=credentials_dict,
        settings_manager=settings_manager,
        first_run=first_run,
    )
    ctx.register("sql_db", SqlDBUtility(ctx))
    return ctx


def parse_args():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--reason",
        choices=["lost", "tp", "sl", "tsl", "timeout", "manual"],
        help="Filter by trigger_reason/exit_reason",
    )
    parser.add_argument(
        "--today",
        action="store_true",
        help="Limit to today's trades (00:00–00:00 in local time)",
    )
    parser.add_argument(
        "--since",
        type=str,
        help="Limit to trades since this date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Process all tokens (no trade filter)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Optional max number of tokens to process",
    )

    return parser.parse_args()


def get_bounds_from_args(args):
    from_ts = None
    to_ts = None

    if args.today:
        now_local = datetime.now().astimezone()
        start = datetime.combine(now_local.date(), datetime.min.time(), tzinfo=now_local.tzinfo)
        end = start + timedelta(days=1)
        from_ts, to_ts = start, end
    elif args.since:
        from_ts = datetime.fromisoformat(args.since).astimezone()
        # open-ended [from_ts, ∞)

    return from_ts, to_ts


def map_reason_to_db(reason_cli: str) -> str:
    """Map CLI reason names to DB trigger_reason/exit_reason."""
    mapping = {
        "lost": "LOST",
        "tp": "TP",
        "sl": "SL",
        "tsl": "TSL",
        "timeout": "TIMEOUT",
        "manual": "MANUAL",
    }
    return mapping.get(reason_cli)


def load_mints(args):
    ctx = build_context()
    dao = TokenDAO(ctx)

    if args.all:
        rows = dao.fetch_mint_signature() 
    else:
        trigger_reason = map_reason_to_db(args.reason) if args.reason else None
        from_ts, to_ts = get_bounds_from_args(args)
        rows = dao.fetch_mint_signature(
            trigger_reason=trigger_reason,
            from_ts=from_ts,
            to_ts=to_ts,
        )

    if not rows:
        return pd.DataFrame(columns=["signature", "token_address"])

    df = pd.DataFrame(rows, columns=["signature", "token_address"])

    if args.limit:
        df = df.head(args.limit)

    return df


def run_extractor(signature, token):
    if not signature or str(signature).lower() == "none":
        return

    print(f"🚀 Extracting logs for {token} ({signature})")
    subprocess.run(
        ["python", EXTRACTOR_SCRIPT, "--signature", signature, "--token", token]
    )


def run_all_parallel(df: pd.DataFrame):
    tasks = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        for _, row in df.iterrows():
            signature = row["signature"]
            token = row["token_address"]
            tasks.append(executor.submit(run_extractor, signature, token))

        for task in as_completed(tasks):
            try:
                task.result()
            except Exception as e:
                print(f"❌ Error during log extraction: {e}")

    print("\n✅ Mint signature extraction completed!")


def main():
    args = parse_args()
    df = load_mints(args)

    if df.empty:
        print("⚠️ No tokens match the filter.")
        return

    run_all_parallel(df)


if __name__ == "__main__":
    main()
