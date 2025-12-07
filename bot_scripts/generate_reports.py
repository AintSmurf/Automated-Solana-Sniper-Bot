import pandas as pd

from dao.token_dao import TokenDAO
from services.bot_context import BotContext
from helpers.credentials_utility import CredentialsUtility
from config.settings import Settings
from services.sql_db_utility import SqlDBUtility
from helpers.framework_utils import get_local_tz_offset_str
SINCE_TIMESTAMP = "2025-12-06 00:00:00"

def main():
    # ── bootstrap context / db ─────────────────────────
    credentials = CredentialsUtility()
    credentials_dictionary = credentials.get_all()

    settings_manager = Settings()
    first_run = settings_manager.is_first_run()
    bot_settings = settings_manager.load_settings()
    settings_manager.validate_bot_settings(bot_settings)

    ctx = BotContext(
        settings=bot_settings,
        api_keys=credentials_dictionary,
        settings_manager=settings_manager,
        first_run=first_run,
    )
    ctx.register("sql_db", SqlDBUtility(ctx))

    tk = TokenDAO(ctx)

    # ── base data ──────────────────────────────────────
    tz_offset_str = get_local_tz_offset_str()
    since_ts = SINCE_TIMESTAMP


    summary_rows = tk.produce_summary_results(since_ts)
    per_session_rows = tk.produce_summary_per_date(tz_offset_str, since_ts)

    exit_rule_rows = tk.produce_exit_rule_stats(since_ts)
    liquidity_rows = tk.produce_liquidity_stats(since_ts)
    safety_rows = tk.produce_safety_score_stats(since_ts)
    hold_rows = tk.produce_hold_duration_stats(since_ts)
    age_rows = tk.produce_token_age_stats(since_ts)

    export_to_excel(
        summary_rows=summary_rows,
        per_session_rows=per_session_rows,
        exit_rule_rows=exit_rule_rows,
        liquidity_rows=liquidity_rows,
        safety_rows=safety_rows,
        hold_rows=hold_rows,
        age_rows=age_rows,
    )


def export_to_excel(
    summary_rows,
    per_session_rows=None,
    exit_rule_rows=None,
    liquidity_rows=None,
    safety_rows=None,
    hold_rows=None,
    age_rows=None,
):
    output_path = "summary_results_2.xlsx"

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        # ── Sheet 1: per-trade summary ──────────────────
        if summary_rows:
            summary_columns = [
                "token",
                "buy_event",
                "sell_event",
                "buy_price",
                "sell_price",
                "profit_percent",
                "exit_reason",
                "post_buy_score",
                "marketcap",
            ]
            df = pd.DataFrame(summary_rows, columns=summary_columns)

            df["buy_price"] = pd.to_numeric(df["buy_price"], errors="coerce")
            df["sell_price"] = pd.to_numeric(df["sell_price"], errors="coerce")
            df["profit_percent"] = pd.to_numeric(df["profit_percent"], errors="coerce")
            df["marketcap"] = pd.to_numeric(df["marketcap"], errors="coerce")

            df.to_excel(writer, index=False, sheet_name="Summary")
            ws = writer.sheets["Summary"]
            for row in ws.iter_rows(min_row=2):
                row[3].number_format = "0.000000"  # buy_price
                row[4].number_format = "0.000000"  # sell_price
                row[5].number_format = "0.00"      # profit_percent
                row[8].number_format = "0"         # marketcap

        # ── Sheet 2: per-session expectancy ─────────────
        if per_session_rows:
            per_session_columns = [
                "session_date",
                "trade_count",
                "total_pnl_percent",
                "avg_pnl_percent",
                "winning_trades",
                "losing_trades",
            ]
            per_session_df = pd.DataFrame(per_session_rows, columns=per_session_columns)
            per_session_df.to_excel(writer, index=False, sheet_name="PerSession")
            ws2 = writer.sheets["PerSession"]
            for row in ws2.iter_rows(min_row=2):
                row[2].number_format = "0.00"  # total_pnl_percent
                row[3].number_format = "0.00"  # avg_pnl_percent

        # ── Sheet 3: exit-rule performance ──────────────
        if exit_rule_rows:
            exit_columns = [
                "trigger_reason",
                "trade_count",
                "avg_pnl_percent",
                "median_pnl_percent",
                "p95_pnl_percent",
                "total_profit_usd",
                "avg_profit_usd",
            ]
            exit_df = pd.DataFrame(exit_rule_rows, columns=exit_columns)
            exit_df.to_excel(writer, index=False, sheet_name="ExitRules")

        # ── Sheet 4: liquidity buckets ──────────────────
        if liquidity_rows:
            liq_columns = [
                "liq_bucket",
                "trade_count",
                "avg_pnl_percent",
                "total_profit_usd",
                "avg_profit_usd",
            ]
            liq_df = pd.DataFrame(liquidity_rows, columns=liq_columns)
            liq_df.to_excel(writer, index=False, sheet_name="LiquidityBuckets")

        # ── Sheet 5: safety score buckets ───────────────
        if safety_rows:
            safety_columns = [
                "score_bucket",
                "trade_count",
                "avg_pnl_percent",
                "total_profit_usd",
            ]
            safety_df = pd.DataFrame(safety_rows, columns=safety_columns)
            safety_df.to_excel(writer, index=False, sheet_name="SafetyScore")

        # ── Sheet 6: hold duration ──────────────────────
        if hold_rows:
            hold_columns = [
                "hold_bucket",
                "trade_count",
                "avg_hold_seconds",
                "avg_pnl_percent",
                "total_profit_usd",
            ]
            hold_df = pd.DataFrame(hold_rows, columns=hold_columns)
            hold_df.to_excel(writer, index=False, sheet_name="HoldDuration")

        # ── Sheet 7: token age at buy ───────────────────
        if age_rows:
            age_columns = [
                "age_bucket",
                "trade_count",
                "avg_age_seconds",
                "avg_pnl_percent",
                "total_profit_usd",
            ]
            age_df = pd.DataFrame(age_rows, columns=age_columns)
            age_df.to_excel(writer, index=False, sheet_name="TokenAge")

    print("✅ Excel file saved with all reports:", output_path)


if __name__ == "__main__":
    main()
