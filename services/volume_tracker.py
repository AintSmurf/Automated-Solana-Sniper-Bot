import time
from collections import deque
from services.bot_context import BotContext
from concurrent.futures import Future
from config.dex_detection_rules import KNOWN_BASES



class VolumeTracker:
    def __init__(self, ctx: BotContext):
        self.ctx = ctx
        self.volume_by_token = {}
        self.token_launch_info = {}
        self.volume_futures: dict[str, Future] = {}
        self.logger = ctx.get("logger")

    def record_trade(self, token_mint: str, volume: dict, signature: str)->None:
        now = time.time()
        if token_mint not in self.volume_by_token:
            self.volume_by_token[token_mint] = deque(maxlen=10000)

        # Record buys
        if volume.get("buy_usd", 0) > 0:
            self.volume_by_token[token_mint].append((now, volume["buy_usd"], "buy", signature))

        # Record sells
        if volume.get("sell_usd", 0) > 0:
            self.volume_by_token[token_mint].append((now, volume["sell_usd"], "sell", signature))

    def snapshot_launch(self, token_mint: str, timestamp: int, first_trade_usd: float, signature: str) -> None:
        self.token_launch_info[token_mint] = {
            "launch_time": timestamp,
            "launch_volume": first_trade_usd,
            "first_signature": signature,
            "last_snapshot": first_trade_usd,
            "last_buy": 0.0,
            "last_sell": 0.0,
        }
  
    def stats(self, token_mint: str, window=300) -> dict:
        now = time.time()
        trades = self.volume_by_token.get(token_mint, [])
        if window:
            recent = [(ts, usd, ttype, sig) for ts, usd, ttype, sig in trades if now - ts <= window]
        else:
            recent = trades

        total_buy = sum(usd for _, usd, ttype, _ in recent if ttype == "buy")
        total_sell = sum(usd for _, usd, ttype, _ in recent if ttype == "sell")

        total_usd = total_buy + total_sell

        launch = self.token_launch_info.get(token_mint, {})
        launch_time = launch.get("launch_time")
        launch_volume = launch.get("launch_volume", 0.0)

        delta_volume = max(total_usd - launch_volume, 0) if launch_volume else total_usd

        return {
            "count": len(recent),
            "buy_usd": round(total_buy, 2),
            "sell_usd": round(total_sell, 2),
            "total_usd": round(total_usd, 2),
            "buy_count": sum(1 for _, _, ttype, _ in recent if ttype == "buy"),
            "sell_count": sum(1 for _, _, ttype, _ in recent if ttype == "sell"),
            "buy_ratio": round((total_buy / total_usd * 100) if total_usd > 0 else 0, 2),
            "net_flow": round(total_buy - total_sell, 2),
            "launch_time": launch_time,
            "launch_volume": round(launch_volume, 2),
            "delta_volume": round(delta_volume, 2),
        }
  
    def parse_helius_swap_volume(self, pool_address: str) -> dict:
        volumes = {}
        try:
            response = self.ctx.get("helius_client").get_enhanced_transactions_by_address(pool_address)
        except Exception as e:
            self.logger.error(f"❌ Error fetching transactions for {pool_address}: {e}")
            return {}

        try:
            sol_price = self.ctx.get("jupiter_client").get_sol_price()
        except Exception as e:
            self.logger.warning(f"⚠️ Failed to fetch SOL price: {e}")
            sol_price = 0.0

        for tx in response:
            transfers = tx.get("tokenTransfers", [])
            if not transfers:
                continue

            for t in transfers:
                mint = t.get("mint")
                frm = t.get("fromUserAccount")
                to = t.get("toUserAccount")
                try:
                    amount = float(t.get("tokenAmount", 0) or 0)
                except (TypeError, ValueError):
                    amount = 0.0
                if not mint or amount <= 0:
                    continue
                base_info = KNOWN_BASES.get(mint)
                if not base_info:
                    continue
                symbol = base_info["symbol"]
                if symbol == "SOL":
                    usd_value = amount * sol_price
                elif symbol in {"USDC", "USDT", "USD1"}:
                    usd_value = amount
                else:
                    continue
                if usd_value <= 0:
                    continue
                if frm == pool_address:
                    self._accumulate(volumes, mint, "sell", usd_value)
                elif to == pool_address:
                    self._accumulate(volumes, mint, "buy", usd_value)

        total_usd = sum(v["total_usd"] for v in volumes.values())
        self.logger.info(f"✅ Finished volume extraction — {len(volumes)} tokens, total volume ${total_usd:,.2f}")
        return volumes

    def _accumulate(self, volumes:dict, mint:str, label:str, usd_value:float) -> None:
        if mint not in volumes:
            volumes[mint] = {"buy_usd": 0.0, "sell_usd": 0.0}
        volumes[mint][f"{label}_usd"] += usd_value
        volumes[mint]["total_usd"] = volumes[mint]["buy_usd"] + volumes[mint]["sell_usd"]

    def _volume_worker(self, token_mint: str, signature: str, block_time: int) -> None:
        pool_address = self.ctx.get("liquidity_dao").get_pool_address(token_mint)
        if not pool_address:
            self.logger.warning(f"⚠️ No pool address found for {token_mint}, skipping initial volume snapshot.")
            return

        snap = self.parse_helius_swap_volume(pool_address)
        agg_buy = sum(v.get("buy_usd", 0.0) for v in snap.values())
        agg_sell = sum(v.get("sell_usd", 0.0) for v in snap.values())

        self.record_trade(
            token_mint,
            {"buy_usd": agg_buy, "sell_usd": agg_sell, "total_usd": agg_buy + agg_sell},
            signature,
        )
        self.snapshot_launch(token_mint, block_time, agg_buy + agg_sell, signature)

    def check_volume_growth(self, token_mint: str, signature: str) -> None:
        future = self.volume_futures.get(token_mint)
        if future:
            try:
                future.result(timeout=15)
                self.logger.debug(f"⏳ Volume worker finished for {token_mint}.")
            except Exception as e:
                self.logger.warning(f"⚠️ Volume worker not finished for {token_mint}: {e}")

        launch_info = self.token_launch_info.get(token_mint)
        if not launch_info:
            self.logger.warning(f"⚠️ No launch snapshot found for {token_mint}, skipping volume growth check.")
            return

        pool_address = self.ctx.get("liquidity_dao").get_pool_address(token_mint)
        if not pool_address:
            self.logger.warning(f"⚠️ No pool address found for {token_mint}, skipping volume growth check.")
            return

        snap_volumes = self.parse_helius_swap_volume(pool_address)

        agg_buy = sum(v.get("buy_usd", 0.0) for v in snap_volumes.values())
        agg_sell = sum(v.get("sell_usd", 0.0) for v in snap_volumes.values())
        total = agg_buy + agg_sell

        prev_total = launch_info.get("last_snapshot", launch_info.get("launch_volume", 0.0))
        delta = max(total - prev_total, 0)

        if delta > 0:
            self.record_trade(
                token_mint,
                {
                    "buy_usd": max(agg_buy - launch_info.get("last_buy", 0.0), 0),
                    "sell_usd": max(agg_sell - launch_info.get("last_sell", 0.0), 0),
                    "total_usd": delta,
                },
                signature=signature,
            )

        launch_info["last_snapshot"] = total
        launch_info["last_buy"] = agg_buy
        launch_info["last_sell"] = agg_sell

        self.logger.debug(
            f"📊 Updated volume delta for {token_mint}: Δ ${delta:,.2f}, total so far ${total:,.2f}"
        )


