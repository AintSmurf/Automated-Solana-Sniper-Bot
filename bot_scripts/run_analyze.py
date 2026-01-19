import argparse
from datetime import datetime, timedelta
import pandas as pd
import subprocess
import os

from dao.token_dao import TokenDAO
from services.bot_context import BotContext
from helpers.credentials_utility import CredentialsUtility
from config.settings import Settings
from services.sql_db_utility import SqlDBUtility

# analyze.py is now the *batch* extractor that expects: --pairs <csv>
EXTRACTOR_SCRIPT = os.path.join(os.path.dirname(__file__), "analyze.py")


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
        choices=["lost", "tp", "sl", "tsl", "timeout", "manual","fail"],
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
        # Note: fromisoformat("YYYY-MM-DD") gives naive datetime; astimezone() makes it local
        from_ts = datetime.fromisoformat(args.since).astimezone()

    return from_ts, to_ts


def map_reason_to_db(reason_cli: str) -> str:
    mapping = {
        "lost": "LOST",
        "tp": "TP",
        "sl": "SL",
        "tsl": "TSL",
        "timeout": "TIMEOUT",
        "manual": "MANUAL",
        "fail":"FAILED",
    }
    return mapping.get(reason_cli)


def load_mints(args):
    ctx = build_context()
    dao = TokenDAO(ctx)

    if args.all:
        rows = dao.fetch_mint_signatures()
    else:
        trigger_reason = map_reason_to_db(args.reason) if args.reason else None
        from_ts, to_ts = get_bounds_from_args(args)
        rows = dao.fetch_mint_signatures(
            trigger_reason=trigger_reason,
            from_ts=from_ts,
            to_ts=to_ts,
        )

    if not rows:
        return pd.DataFrame(columns=[
            "token_address", "mint_signature", "buy_signature", "sell_signature"
        ])

    df = pd.DataFrame(rows, columns=[
        "token_address", "mint_signature", "buy_signature", "sell_signature"
    ])

    # normalize
    df["token_address"] = df["token_address"].fillna("").astype(str)
    for col in ("mint_signature", "buy_signature", "sell_signature"):
        df[col] = df[col].fillna("").astype(str)

    # keep only valid token rows
    df = df[df["token_address"].str.len() > 0]

    # keep rows that have at least ONE signature
    sig_cols = ("mint_signature", "buy_signature", "sell_signature")
    df = df[
        (df["mint_signature"].str.lower().ne("none") & df["mint_signature"].str.len().gt(0)) |
        (df["buy_signature"].str.lower().ne("none") & df["buy_signature"].str.len().gt(0)) |
        (df["sell_signature"].str.lower().ne("none") & df["sell_signature"].str.len().gt(0))
    ]

    if args.limit:
        df = df.head(args.limit)

    return df



def run_batch_extractor(df: pd.DataFrame):
    os.makedirs("logs", exist_ok=True)

    pairs_csv = os.path.join("logs", "pairs.csv")
    df.to_csv(pairs_csv, index=False)

    print(f"🧠 Saved {len(df)} pairs -> {pairs_csv}")
    print(f"🚀 Running batch extractor: {EXTRACTOR_SCRIPT}")

    subprocess.run(
        ["python", EXTRACTOR_SCRIPT, "--pairs", pairs_csv],
        check=True,
    )

    print("\n✅ Mint signature extraction completed!")


def main():
    args = parse_args()
    df = load_mints(args)

    if df.empty:
        print("⚠️ No tokens match the filter.")
        return

    run_batch_extractor(df)


if __name__ == "__main__":
    main()
