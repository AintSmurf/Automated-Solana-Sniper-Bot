from datetime import datetime, timezone
from services.bot_context import BotContext
from helpers.framework_utils import unique_recovery_sig
from config.dex_detection_rules import KNOWN_TOKENS


class WalletReconciliationService:
    def __init__(self, ctx: BotContext):
        self.ctx = ctx
        self.settings = ctx.settings
        self.logger = ctx.get("logger")
        self.notifier = ctx.get("notification_manager")

        self.wallet_client = ctx.get("wallet_client")
        self.trade_dao = ctx.get("trade_dao")
        self.signatures_dao = ctx.get("signatures_dao")
        self.token_dao = ctx.get("token_dao")
        self.jupiter = ctx.get("jupiter_client")
        self.trade_counter = ctx.get("trade_counter")

        self.active_trades = ctx.get("active_trades")
        self.tokens_lock = ctx.get("active_trades_lock")
        self.config_id = ctx.get("config_id")
        self.run_id= ctx.get("run_id")


    def reconcile(self) -> None:
        try:
            sim_mode = self.settings["SIM_MODE"]
            dust_threshold_usd = self.settings["DUST_THRESHOLD_USD"]
            if sim_mode:
                return
            ignored_mints = set(KNOWN_TOKENS.values())
            self.logger.debug(f"Ignoring known base tokens: {', '.join(KNOWN_TOKENS.keys())}")
            wallet_tokens = self._build_wallet_tokens_snapshot(ignored_mints, dust_threshold_usd)
            db_tokens = self._build_open_db_tokens(sim_mode)
            self._repair_db_trades_found_in_wallet(wallet_tokens, db_tokens, ignored_mints)
            self._recover_wallet_tokens_missing_from_db(wallet_tokens, db_tokens, ignored_mints)
            self._close_db_trades_missing_from_wallet(wallet_tokens, db_tokens, ignored_mints)
            self.logger.info(f"🔍 Reconciliation complete — Wallet={len(wallet_tokens)}, DB(open-ish)={len(db_tokens)}")

        except Exception as e:
            self.logger.error(f"❌ Wallet↔DB reconciliation failed: {e}", exc_info=True)

    def _build_wallet_tokens_snapshot(self,ignored_mints: set[str],dust_threshold_usd: float,) -> dict[str, float]:
        wallet_balances = self.wallet_client.get_token_balances()
        wallet_tokens: dict[str, float] = {}
        price_cache: dict[str, float] = {}

        for balance_row in wallet_balances:
            token_mint = balance_row["token_mint"]
            balance = float(balance_row["balance"])

            if token_mint in ignored_mints:
                continue

            if token_mint not in price_cache:
                try:
                    price_cache[token_mint] = self.jupiter.get_token_price(token_mint) or 0.0
                except Exception as e:
                    self.logger.warning(f"Failed to fetch price for {token_mint}: {e}")
                    price_cache[token_mint] = 0.0

            usd_price = float(price_cache[token_mint] or 0.0)
            usd_value = balance * usd_price

            if usd_value < dust_threshold_usd:
                continue

            wallet_tokens[token_mint] = balance

        return wallet_tokens

    def _build_open_db_tokens(self, sim_mode: bool) -> dict[str, dict]:
        submitted = self.trade_dao.get_submitted_trades(sim_mode)
        live = self.trade_dao.get_live_trades(sim_mode)

        try:
            selling = self.trade_dao.get_selling_trades(sim_mode)
        except Exception:
            selling = []

        open_trades = submitted + live + selling

        db_tokens: dict[str, dict] = {}
        for trade in open_trades:
            addr = trade.get("token_address")
            if addr and addr not in db_tokens:
                db_tokens[addr] = trade

        return db_tokens

    def _repair_db_trades_found_in_wallet( self, wallet_tokens: dict[str, float], db_tokens: dict[str, dict], ignored_mints: set[str],) -> None:
        for token_mint, _bal in wallet_tokens.items():
            if token_mint in ignored_mints:
                continue

            if token_mint not in db_tokens:
                continue

            db_trade = db_tokens[token_mint]
            status = str(db_trade.get("status", "")).upper()

            with self.tokens_lock:
                self.active_trades[token_mint] = db_trade

            if status in ("SUBMITTED", "CONFIRMED", "BUY_FAILED", "BUY_TIMEOUT"):
                try:
                    self.trade_dao.update_trade_status_with_ts(db_trade["id"], "FINALIZED")

                    did_repair = False
                    with self.tokens_lock:
                        if token_mint in self.active_trades:
                            self.active_trades[token_mint]["status"] = "FINALIZED"
                            did_repair = True

                    if did_repair:
                        try:
                            self.trade_counter.increment()
                        except Exception:
                            pass

                    self.logger.warning(
                        f"🩹 Reconcile repaired {status} -> FINALIZED via WALLET for {token_mint}"
                    )
                except Exception as e:
                    self.logger.warning(
                        f"⚠️ Failed to repair status -> FINALIZED for {token_mint}: {e}"
                    )

                try:
                    buy_sig = self.signatures_dao.get_buy_signature(db_trade["token_id"])
                    if not buy_sig:
                        self.signatures_dao.upsert_buy_signature(
                            db_trade["token_id"],
                            unique_recovery_sig(),
                        )
                except Exception:
                    pass

    def _recover_wallet_tokens_missing_from_db(self,wallet_tokens: dict[str, float],db_tokens: dict[str, dict],ignored_mints: set[str],) -> None:
        price_cache: dict[str, float] = {}

        for token_mint, bal in wallet_tokens.items():
            if token_mint in ignored_mints or token_mint in db_tokens:
                continue

            latest = self.trade_dao.get_latest_trade_by_token_any_status(token_mint)
            if latest:
                latest_status = str(latest.get("status", "")).upper()
                latest_reason = str(latest.get("trigger_reason", "")).upper()

                if latest_status == "CLOSED" and latest_reason == "WALLET_MISSING":
                    closed_at = latest.get("closed_at")
                    if isinstance(closed_at, datetime) and closed_at.tzinfo is None:
                        closed_at = closed_at.replace(tzinfo=timezone.utc)

                    if closed_at and (datetime.now(timezone.utc) - closed_at).total_seconds() < 300:
                        self.trade_dao.reopen_trade(latest["id"], status="FINALIZED")
                        revived = self.trade_dao.get_trade_by_id(latest["id"])

                        with self.tokens_lock:
                            self.active_trades[token_mint] = revived

                        self.logger.warning(
                            f"🩹 Revived WALLET_MISSING -> FINALIZED for {token_mint}"
                        )
                        continue

            self.notifier.notify_text(
                f"🩹 **Recovered Token** — `{token_mint}` added to DB\n💰 Balance: {bal:.6f}"
            )
            self.logger.warning(
                f"🩹 Found token in wallet but not DB: {token_mint} (balance={bal}) — creating recovery trade"
            )

            if token_mint not in price_cache:
                try:
                    price_cache[token_mint] = self.jupiter.get_token_price(token_mint) or 0.0
                except Exception:
                    price_cache[token_mint] = 0.0

            entry_usd = float(price_cache.get(token_mint) or 0.0)
            token_id = self.token_dao.get_or_create_token(token_mint, None)

            trade_id = self.trade_dao.insert_trade(
                token_id=token_id,
                trade_type="BUY",
                entry_usd=entry_usd,
                simulation=self.settings["SIM_MODE"],
                status="RECOVERED",
                config_id=self.config_id,
                run_id=self.run_id,
            )
            self.signatures_dao.upsert_buy_signature(
                token_id,
                buy_signature=unique_recovery_sig(),
            )
            trade = self.trade_dao.get_trade_by_id(trade_id)

            try:
                self.trade_counter.increment()
            except Exception:
                pass

            with self.tokens_lock:
                self.active_trades[token_mint] = trade

    def _close_db_trades_missing_from_wallet(self,wallet_tokens: dict[str, float],db_tokens: dict[str, dict],ignored_mints: set[str],) -> None:
        for token_mint, trade in db_tokens.items():
            if token_mint in ignored_mints:
                continue

            status = str(trade.get("status", "")).upper()
            if status in ("SUBMITTED", "CONFIRMED", "SELLING", "SELL_TIMEOUT", "EXIT_REQUESTED"):
                continue

            if token_mint in wallet_tokens:
                continue

            self.notifier.notify_text(
                f"🧹 **Wallet Missing Token** — `{token_mint}` closing as LOST"
            )
            self.logger.warning(
                f"🧹 Token missing in wallet but open in DB: {token_mint} — closing trade as WALLET_MISSING"
            )

            try:
                self.trade_dao.close_trade(
                    trade_id=trade["id"],
                    exit_usd=0.0,
                    pnl_percent=-100.0,
                    trigger_reason="WALLET_MISSING",
                )
            except Exception as e:
                self.logger.warning(f"⚠️ Failed to close WALLET_MISSING for {token_mint}: {e}")

            with self.tokens_lock:
                self.active_trades.pop(token_mint, None)