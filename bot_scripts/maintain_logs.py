import datetime
import json
import os
import sys

from bot_scripts import shrink_logs
from bot_scripts import run_analyze 


CONFIG_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "config", "logs_config.json"))

def load_log_config():
    if not os.path.exists(CONFIG_PATH):
        print(f"ℹ️ No logs_config.json found at {CONFIG_PATH}, nothing to do.")
        return None

    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"❌ Failed to load logs_config.json: {e}")
        return None

def _run_shrink_logs(auto_gzip, auto_delete, retention_days, include_backups):
    if not auto_gzip and not auto_delete:
        print("ℹ️ AUTO_GZIP and AUTO_DELETE both disabled, skipping shrink.")
        return

    if auto_gzip and auto_delete:
        print("❌ Both AUTO_GZIP and AUTO_DELETE are True. Please choose one.")
        return

    mode = "gzip" if auto_gzip else "delete"

    today = datetime.date.today()
    cutoff_date = today - datetime.timedelta(days=retention_days)
    cutoff_str = cutoff_date.isoformat()

    print(
        f"🧹 Auto log maintenance: mode={mode}, before={cutoff_str}, "
        f"include_backups={include_backups}"
    )
    sys.argv = [
        "shrink_logs",
        "--before",
        cutoff_str,
        "--mode",
        mode,
    ] + (["--include-backups"] if include_backups else [])

    shrink_logs.main()

def _run_auto_analyze_today():
    """Run batch analysis for today's tokens."""
    print("📊 Auto-analyzing tokens for today (all reasons)...")
    sys.argv = [
        "run_analyze",
        "--today",
    ]
    run_analyze.main()

def main():
    log_cfg = load_log_config()
    if not log_cfg:
        return

    auto_analyze = log_cfg.get("AUTO_ANALYZE_TOKENS", False)
    auto_gzip = log_cfg.get("AUTO_GZIP", False)
    auto_delete = log_cfg.get("AUTO_DELETE", False)
    retention_days = int(log_cfg.get("RETENTION_DAYS", 2))
    include_backups = bool(log_cfg.get("INCLUDE_BACKUPS", True))

    if not auto_analyze and not auto_gzip and not auto_delete:
        print("ℹ️ Nothing enabled in logs_config.json, exiting.")
        return
    if auto_gzip or auto_delete:
        _run_shrink_logs(auto_gzip, auto_delete, retention_days, include_backups)
    if auto_analyze:
        _run_auto_analyze_today()

if __name__ == "__main__":
    main()
