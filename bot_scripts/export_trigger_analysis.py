import re
import pandas as pd

from dao.token_dao import TokenDAO
from services.bot_context import BotContext
from helpers.credentials_utility import CredentialsUtility
from config.settings import Settings
from services.sql_db_utility import SqlDBUtility

SINCE_TS = "2025-12-25 00:00:00"
OUTPUT_PATH = "trigger_analysis.xlsx"

feature_columns = [
    "trade_id","token_id","trade_ts","trade_type","entry_usd","exit_usd","pnl_percent",
    "trigger_reason","status","simulation",
    "market_cap","holders_count",
    "total_liq","sol_liq","usdc_liq","usdt_liq","usd1_liq",
    "net_flow","delta_volume","buy_usd","sell_usd","total_usd",
    "buy_count","sell_count","buy_ratio",
    "safety_score",
]

def safe_sheet_name(name: str) -> str:
    name = re.sub(r'[:\\/?*\[\]]', "_", name).strip()
    return name[:31] if name else "Sheet"

def rows_to_df(rows):
    if not rows:
        return pd.DataFrame(columns=feature_columns)
    if isinstance(rows[0], dict):
        return pd.DataFrame(rows).reindex(columns=feature_columns)
    return pd.DataFrame(rows, columns=feature_columns)

def write_feature_sheet(writer, sheet_name: str, rows):
    if not rows:
        return
    df = rows_to_df(rows)

    df["pnl_percent"] = pd.to_numeric(df["pnl_percent"], errors="coerce")
    df = df.sort_values("pnl_percent", ascending=True)

    num_cols = [
        "entry_usd","exit_usd","market_cap","holders_count",
        "total_liq","net_flow","delta_volume","safety_score",
        "buy_usd","sell_usd","total_usd","buy_count","sell_count","buy_ratio",
    ]
    for c in num_cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    df.to_excel(writer, index=False, sheet_name=sheet_name)

def main():
    # bootstrap
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
    all_rows = tk.fetch_trades_with_features(since_ts=SINCE_TS, mode="detail") or []
    all_df = rows_to_df(all_rows)

    with pd.ExcelWriter(OUTPUT_PATH, engine="openpyxl") as writer:
        if not all_df.empty:
            all_df["buy_ratio"] = pd.to_numeric(all_df["buy_ratio"], errors="coerce")
            all_df["net_flow"] = pd.to_numeric(all_df["net_flow"], errors="coerce")
            all_df["total_liq"] = pd.to_numeric(all_df["total_liq"], errors="coerce")
            all_df["pnl_percent"] = pd.to_numeric(all_df["pnl_percent"], errors="coerce")
            all_df["is_sl"] = all_df["trigger_reason"].isin(["SL", "TSL"])

            all_df["buy_ratio_bucket"] = pd.cut(
                all_df["buy_ratio"],
                bins=[0, 45, 50, 55, 60, 100],
                right=False,
                include_lowest=True,
            )

            analysis = (
                all_df.groupby("buy_ratio_bucket", dropna=False)
                .agg(
                    trades=("trade_id", "count"),
                    avg_pnl=("pnl_percent", "mean"),
                    sl_rate=("is_sl", "mean"),
                    avg_net_flow=("net_flow", "mean"),
                    avg_liq=("total_liq", "mean"),
                )
                .reset_index()
            )
            analysis.to_excel(writer, index=False, sheet_name="Analysis_BuyRatio")
        reasons = tk.list_trigger_reasons(SINCE_TS)
        used = set()
        for reason in reasons:
            rows = tk.fetch_trades_with_features(
                since_ts=SINCE_TS,
                trigger_reasons=[reason],
                mode="detail",
            ) or []

            sheet = safe_sheet_name(f"TR_{reason}")
            if sheet in used:
                sheet = safe_sheet_name(sheet + "_2")
            used.add(sheet)

            write_feature_sheet(writer, sheet, rows)
        big_loss_rows = tk.fetch_trades_with_features(
            since_ts=SINCE_TS,
            pnl_lte=-50,
            mode="detail",
        ) or []
        write_feature_sheet(writer, "BigLosses_All", big_loss_rows)

    print("✅ Saved:", OUTPUT_PATH)

if __name__ == "__main__":
    main()
