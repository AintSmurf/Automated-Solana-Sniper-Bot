import time
from config.blacklist import BLACK_LIST
from config.dex_detection_rules import KNOWN_TOKENS
from helpers.framework_utils import run_bg,run_timer,run_prefetch
from threading import Event
from services.bot_context import BotContext
from queue import Empty
from threading import Event


class TransactionManager:
    def __init__(self, ctx:BotContext):
        self.ctx = ctx
        self.logger = ctx.get("logger")
        st = ctx.settings
        self.network = st["NETWORK"]
        self.max_age = st["MAX_TOKEN_AGE_SECONDS"]
        self.min_liq = st["MIN_TOKEN_LIQUIDITY"]
        self.trade_amount = st["TRADE_AMOUNT"]
        self.sim_mode = st["SIM_MODE"]
        self.new_tokens_channel = ctx.settings_manager.get_notification_settings()["DISCORD"]["NEW_TOKENS_CHANNEL"]

        self.flow_timer_by_token = {}

    def run(self, stop_event: Event) -> None:
        while not stop_event.is_set():
            try:
                sig, tx_data, token_mint, source = self.ctx.get("prefetch_queue").get_nowait()
            except Empty:
                try:
                    sig, tx_data, token_mint, source = self.ctx.get("signature_queue").get(timeout=0.5)
                except Empty:
                    continue

            self.logger.debug(f"⚡ Processing signature {sig} from {source}")
            self.process_signature(sig, tx_data, token_mint)

    def process_signature(self, signature: str,tx_data=None, token_mint:str=None)->None:
        """Fetch tx, decide if interesting, maybe buy, notify, volume, etc."""
        try:
            if not tx_data:
                tx_data = self.ctx.get("solana_manager").get_transaction_data(signature)
                if not tx_data:
                    self.logger.warning(f"❌ Could not fetch transaction data for: {signature}")
                    return
            result = tx_data  
            blocktime = result.get("blockTime")    

            if not token_mint:
                token_mint = self.ctx.get("solana_manager").extract_token_mint(tx_data)
                if not token_mint:
                    return
            #map signature to token
            self.ctx.get("sig_to_mint")[signature] = token_mint
            
            #start timer and prefecth transactions
            self.start_flow_timer(token_mint)
            run_prefetch(self._prefetch, token_mint, name=f"prefetch-{token_mint[:6]}")      
            if token_mint in BLACK_LIST:
                self.logger.info(f"⛔ Blacklisted token {token_mint}, skipping.")
                return
            
            #if token in base tokens ignore
            if token_mint in KNOWN_TOKENS.values():
                return
            
            #if token has liquidity dont proccess it again
            with self.ctx.get("known_tokens_lock"):
                if token_mint in self.ctx.get("known_tokens"):
                    self._cleanup_mint(token_mint)
                    return

            # age
            age = self.ctx.get("solana_manager").get_token_age(token_mint)
            if age is None or age > self.max_age:
                self.logger.info(f"⏳ Token too old / not resolved (age={age}), skip {token_mint}.")
                self._cleanup_mint(token_mint)
                return

            #liquidity check
            if not self.ctx.get("solana_manager").analyze_liquidty(result, token_mint, self.min_liq):
                return

            self.logger.info(f"✅ Passed liquidity test — {token_mint}")

            
            market_cap = self.ctx.get("solana_manager").get_token_marketcap(token_mint)

            # record new token
            pending = self.ctx.get("pending_data").pop(token_mint, None)
            if pending:
                try:
                    token_id = self.ctx.get("token_dao").insert_new_token(signature, token_mint)

                    pool_addr = pending.get("pool_address")
                    dex = pending.get("dex")
                    if pool_addr and dex:
                        self.ctx.get("liquidity_dao").insert_pool(token_id, pool_addr, dex)

                    self.ctx.get("liquidity_dao").insert_snapshot(token_id, pending)
                except Exception as db_err:
                    self.logger.error(f"💾 DB insert failed for {token_mint}: {db_err}", exc_info=True)
            
            # scam checks
            if not self.ctx.get("solana_manager").first_phase_tests(token_mint):
                self.logger.warning(f"❌ Scam check failed — skipping {token_mint}")
                self._cleanup_mint(token_mint)
                return
            
            #add tokens passed liquidity and first pahse of tests
            with self.ctx.get("known_tokens_lock"):   
                self.ctx.get("known_tokens").add(token_mint)
                self._cleanup_mint(token_mint)

            # volume snapshot async
            future = run_bg(self.ctx.get("volume_tracker")._volume_worker, token_mint,signature,blocktime, name=f"vol-{token_mint[:6]}")
            self.ctx.get("volume_tracker").volume_futures[token_mint] = future


            # BUY / SIM
            if not self.ctx.get("trade_counter").reached_limit():
                self.ctx.get("solana_manager").buy("So11111111111111111111111111111111111111112", token_mint, self.trade_amount, self.sim_mode)
            else:
                self.logger.critical("💥 MAXIMUM_TRADES reached — skipping trade.")
            
            #get token metadata
            name,image,_=self.ctx.get("helius_client").get_token_meta_data(token_mint)


            # Notify
            dur = self._pop_flow_duration(token_mint)
            msg = (
                f"🟢 **New token detected**\n"
                f"• token_name:`{name}`\n"
                f"• token_address: `{token_mint}`\n"
                f"• signature: `{signature}`\n"
                f"• Flow duration: {dur:,.2f}\n"
            )
            self.ctx.get("notification_manager").notify_text(msg, self.new_tokens_channel)

            # delayed post-buy checks
            run_timer(
                60.0,
                self._delayed_post_buy_handler,
                token_mint,signature, market_cap,
                name=f"postcheck-{token_mint[:6]}"
            )

        except Exception as e:
            self.logger.error(f"❌ process_signature error: {e}", exc_info=True)
    
    def _cleanup_mint(self, token_mint: str) -> None:
        for sig, mint in list(self.ctx.get("sig_to_mint").items()):
            if mint == token_mint:
                self.ctx.get("sig_to_mint").pop(sig, None)
        try:
            q = self.ctx.get("signature_queue")
            items = []
            while not q.empty():
                sig, tx_data, mint, source = q.get_nowait()
                if mint != token_mint:
                    items.append((sig, tx_data, mint, source))
            for item in items:
                q.put(item)
        except Exception:
            pass
        try:
            q = self.ctx.get("prefetch_queue")
            items = []
            while not q.empty():
                sig, tx_data, mint, source = q.get_nowait()
                if mint != token_mint:
                    items.append((sig, tx_data, mint, source))
            for item in items:
                q.put(item)
        except Exception:
            pass

        self.logger.debug(f"🧹 Cleaned up {token_mint} from queues + sig map")

    def start_flow_timer(self, token_mint:str)->None:
        if token_mint not in self.flow_timer_by_token:
            self.flow_timer_by_token[token_mint] = time.time()

    def _pop_flow_duration(self, token_mint:str)->float:
        start = self.flow_timer_by_token.pop(token_mint, None)
        return (time.time() - start) if start else 0.0

    def _prefetch(self, token_mint: str):
        try:
            sinagures = self.ctx.get("solana_manager").get_recent_transactions_signatures_for_token(token_mint)
            for tx_sig in sinagures[1:5]:
                with self.ctx.get("signature_seen_lock"):
                    if tx_sig in self.ctx.get("signature_seen"):
                        continue
                    self.ctx.get("signature_seen").add(tx_sig)
                self.ctx.get("prefetch_queue").put((tx_sig, None, token_mint, "PREFETCH"))
                self.logger.debug(f"🧊 Queued early tx: {tx_sig}")
        except Exception as e:
            self.logger.error(f"❌ Prefetch extra txs failed for {token_mint}: {e}")

    def _delayed_post_buy_handler(self, token_mint: str, signature: str, market_cap: float, attempt: int = 1):
        try:
            self.logger.info(f"⏳ Running delayed post-buy handler (attempt {attempt}) for {token_mint}...")
            sol_mgr = self.ctx.get("solana_manager")
            res = sol_mgr.second_phase_tests(token_mint, signature, market_cap) or {}
            score = res.get("score", 0)

            min_score = self.ctx.settings.get("MIN_POST_BUY_SCORE", 3)
            self.logger.info(
                f"🛡️ Post-buy score for {token_mint}: {score} (min required={min_score})"
            )

            if score >= min_score:
                return
            opt = self.ctx.get("open_position_tracker")
            if not opt:
                self.logger.warning("⚠️ open_position_tracker not registered in ctx, cannot BAD_SCORE-close.")
                return

            self.logger.info(
                f"🛑 BAD_SCORE for {token_mint} (score={score} < {min_score}) — closing via OpenPositionTracker"
            )
            closed = opt.manual_close(token_mint, trigger="POST_BUY_SCORE")
            if not closed:
                self.logger.warning(
                    f"⚠️ BAD_SCORE manual_close failed or trade not active for {token_mint}"
                )

        except Exception as e:
            self.logger.error(
                f"❌ _delayed_post_buy_handler failed for {token_mint}: {e}",
                exc_info=True
            )

