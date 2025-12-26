import pandas as pd
from dao.token_dao import TokenDAO
from services.bot_context import BotContext
from helpers.credentials_utility import CredentialsUtility
from config.settings import Settings
from services.sql_db_utility import SqlDBUtility
from helpers.framework_utils import get_local_tz_offset_str


def main():
    credentials = CredentialsUtility()
    credentials_dictionary = credentials.get_all()
    
    settings_manager = Settings()
    first_run = settings_manager.is_first_run()
    bot_settings = settings_manager.load_settings()
    settings_manager.validate_bot_settings(bot_settings)

    ctx = BotContext(settings=bot_settings,api_keys=credentials_dictionary,settings_manager=settings_manager, first_run=first_run)
    ctx.register("sql_db", SqlDBUtility(ctx))

    tk = TokenDAO(ctx)
    data = tk.produce_summary_results()
    tz_offset_str = get_local_tz_offset_str()
    per_date_data = tk.produce_summary_per_date(tz_offset_str)
    export_to_excel(data, per_date_data)


def export_to_excel(data, per_date_data=None):
    columns = [
        "token", "buy_event", "sell_event",
        "buy_price", "sell_price",
        "profit_percent", "exit_reason",
        "post_buy_score", "marketcap"
    ]

    df = pd.DataFrame(data, columns=columns)

    df["buy_price"] = pd.to_numeric(df["buy_price"], errors="coerce")
    df["sell_price"] = pd.to_numeric(df["sell_price"], errors="coerce")
    df["profit_percent"] = pd.to_numeric(df["profit_percent"], errors="coerce")
    df["marketcap"] = pd.to_numeric(df["marketcap"], errors="coerce")

    if per_date_data is not None:
        per_date_columns = [
            "session_date",
            "trade_count",
            "total_pnl_percent",
            "avg_pnl_percent",
            "winning_trades",
            "losing_trades",
        ]
        per_date_df = pd.DataFrame(per_date_data, columns=per_date_columns)
    else:
        per_date_df = None

    output_path = "summary_results.xlsx"

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        # Sheet 1
        df.to_excel(writer, index=False, sheet_name="Summary")
        ws = writer.sheets["Summary"]
        for row in ws.iter_rows(min_row=2):
            row[3].number_format = "0.000000"
            row[4].number_format = "0.000000"
            row[5].number_format = "0.00"
            row[8].number_format = "0"

        # Sheet 2 – per 7am session
        if per_date_df is not None:
            per_date_df.to_excel(writer, index=False, sheet_name="PerSession")
            ws2 = writer.sheets["PerSession"]
            for row in ws2.iter_rows(min_row=2):
                row[2].number_format = "0.00"  
                row[3].number_format = "0.00" 

    print("✅ Excel file saved with formatting:", output_path)


if __name__ == "__main__":
    main()