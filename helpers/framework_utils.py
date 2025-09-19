import os
import json
import threading
import traceback
import logging
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import Future
import pandas as pd



logger = logging.getLogger("logger")
bg_executor = ThreadPoolExecutor(max_workers=10)
prefetch_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="prefetch")



# --- Time helpers ---
def convert_blocktime_to_readable_format(blocktime: int) -> str:
    return datetime.fromtimestamp(blocktime).strftime("%H:%M:%S")

def get_diff_between_unix_timestamps(current_time: int, unix_timestamp: int) -> int:
    return current_time - unix_timestamp

def parse_timestamp(raw_str: str):
    formats = ["%Y-%m-%d %H:%M:%S", "%m/%d/%Y %H:%M"] 
    for fmt in formats:
        try:
            return datetime.strptime(raw_str, fmt)
        except ValueError:
            continue
    try:
        return pd.to_datetime(raw_str, errors="raise").to_pydatetime()
    except Exception:
        logger.warning(f"⚠️ Unsupported Buy_Timestamp format: {raw_str}")
        return datetime.now()

# --- File helpers ---
def get_payload(file: str) -> dict:
    path = os.path.join(os.path.dirname(__file__), "..", "data", f"{file}.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

# --- Thread helpers ---
def run_bg(target, *args, name=None, **kwargs) -> Future:
    task_name = name or target.__name__
    def wrapper():
        logger.debug(f"▶️ Background task started: {task_name}")
        try:
            result = target(*args, **kwargs)
            logger.debug(f"✅ Background task finished: {task_name} → {result}")
            return result  
        except Exception:
            logger.error(f"❌ Background thread {task_name} failed:\n{traceback.format_exc()}")
    return bg_executor.submit(wrapper)

def run_timer(delay, target, *args, name=None, **kwargs)->threading:
    def wrapper():
        try:
            target(*args, **kwargs)
        except Exception:
            logger.error(
                f"❌ Timer {name or target.__name__} failed:\n{traceback.format_exc()}"
            )
    def delayed_submit():
        bg_executor.submit(wrapper)
    t = threading.Timer(delay, delayed_submit)
    t.daemon = True
    t.start()
    return t

def run_prefetch(target, *args, name=None, **kwargs) -> Future:
    task_name = name or target.__name__
    def wrapper():
        logger.debug(f"▶️ Prefetch task started: {task_name}")
        try:
            return target(*args, **kwargs)
        except Exception:
            logger.error(f"❌ Prefetch thread {task_name} failed:\n{traceback.format_exc()}")
    return prefetch_executor.submit(wrapper)

# --- math ---
def calculate_tokens(accounts:list):
    token_balances = []
    for acc in accounts:
        mint = acc.get("mint")
        amount = lamports_to_decimal(int(acc.get("amount", 0)),int(acc.get("decimals", 0)))
        token_balances.append({
            "token_mint": mint,
            "balance": amount
        })
    logger.info(f"token_balances: {token_balances}") 
    return token_balances

def lamports_to_decimal(amount: int, decimals: int) -> float:
    return float(amount) / (10 ** decimals)

def decimal_to_lamports(amount: float, decimals: int) -> int:
     return int(amount * (10 ** decimals))

