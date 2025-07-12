import threading
import os
import json
from helpers.logging_manager import LoggingHandler


TRADE_COUNT_FILE = "trade_count.json"
logger = LoggingHandler.get_logger()


class TradeCounter:
    def __init__(self, max_trades):
        self.lock = threading.Lock()
        self.max_trades = max_trades
        self.count = self._load_trade_count()

    def increment(self):
        with self.lock:
            self.count += 1
            self._save_trade_count()
            return self.count

    def reached_limit(self):
        with self.lock:
            return self.count >= self.max_trades

    def get(self):
        with self.lock:
            return self.count

    def _load_trade_count(self):
        if os.path.exists(TRADE_COUNT_FILE):
            try:
                with open(TRADE_COUNT_FILE, "r") as f:
                    return json.load(f).get("count", 0)
            except Exception:
                return 0
        return 0

    def _save_trade_count(self):
        try:
            with open(TRADE_COUNT_FILE, "w") as f:
                json.dump({"count": self.count}, f)
        except Exception as e:
            logger.error(f"Failed to save trade count: {e}")
    
    def reset(self):
        with self.lock:
            self.count = 0
            self._save_trade_count()

