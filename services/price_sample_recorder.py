import time
from datetime import datetime, timezone
from services.bot_context import BotContext


class PriceSampleRecorder:
    def __init__(self, ctx: BotContext):
        self.ctx = ctx
        self.logger = ctx.get("logger")
        self.price_sample_dao = ctx.get("price_sample_dao")
        self.last_bucket_by_token: dict[str, int] = {}
        self.sample_interval = 5

    def maybe_record(self, token_mint: str, trade: dict, current_price_usd: float, pnl: float) -> None:
        bucket = int(time.time() // self.sample_interval)
        if self.last_bucket_by_token.get(token_mint) == bucket:
            return

        try:
            ts = datetime.fromtimestamp(bucket * self.sample_interval, timezone.utc)
            self.price_sample_dao.insert_sample(
                trade_id=trade["id"],
                token_id=trade["token_id"],
                price_usd=current_price_usd,
                pnl_percent=pnl,
                ts=ts,
            )
            self.last_bucket_by_token[token_mint] = bucket
        except Exception as e:
            self.logger.warning(f"⚠️ Failed to insert price sample for {token_mint}: {e}")