from services.bot_context import BotContext


class TradeEnrichmentService:
    def __init__(self, ctx: BotContext):
        self.ctx = ctx
        self.logger = ctx.get("logger")

    def delayed_post_buy_handler(self, token_mint: str, signature: str, market_cap: float,liquidity_snapshot_id:int,attempt: int = 1):
        try:
            trade_dao = self.ctx.get("trade_dao")
            self.logger.info(f"⏳ Running delayed post-buy handler (attempt {attempt}) for {token_mint}...")
            sol_mgr = self.ctx.get("solana_manager")
            res = sol_mgr.second_phase_tests(token_mint, signature, market_cap) or {}
            score = res.get("score", 0)
            results = res.get("results", {})
            holders_count = res.get("holders_count", 0)
            volume_stats = res.get("volume_stats", {})
            mc = res.get("market_cap", market_cap) or 0

            #update DB
            token_id = self.ctx.get("token_dao").get_token_id_by_address(token_mint)
            volume_snapshot_id = None
            if token_id:
                if volume_stats:
                    volume_snapshot_id = self.ctx.get("volume_dao").insert_volume_snapshot(token_id, volume_stats)
                safety_result_id = self.ctx.get("scam_checker_dao").insert_token_results(token_id,results.get("LP_Check", False),results.get("Holders_Check", False),results.get("Volume_Check", False),results.get("MarketCap_Check", False),score,)
                self.ctx.get("token_dao").insert_token_stats(token_id, mc, holders_count)
            trade = trade_dao.get_trade_by_token(token_mint,False)
            trade_id = trade.get("id", 0)

            trade_dao.update_results_ids(trade_id=trade_id,safety_result_id=safety_result_id,volume_snapshot_id=volume_snapshot_id,liquidity_snapshot_id=liquidity_snapshot_id)
            if not trade:
                self.logger.warning( f"⚠️ Delayed post-buy: no trade found for {token_mint} (sig={signature})")
                return

            status = str(trade.get("status", "")).upper()
            if status in ("CLOSED", "BUY_FAILED", "BUY_TIMEOUT"):
                self.logger.info(
                    f"ℹ️ Skipping delayed post-buy close for {token_mint} — trade already {status}"
                )
                return
            
            min_score = self.ctx.settings.get("MIN_POST_BUY_SCORE", 2)
            min_mc = self.ctx.settings.get("MINIMUM_MARKETCAP", 50_000)

            self.logger.info(
                f"🛡️ Post-buy score for {token_mint}: {score} (min required={min_score}), "
                f"marketcap={mc:.0f}, low_mc_thresh={min_mc}"
            )

            opt = self.ctx.get("open_position_tracker")
            if not opt:
                self.logger.warning("⚠️ open_position_tracker not registered in ctx, cannot BAD_SCORE-close.")
                return
            if score <= 1:
                trigger = f"BAD_SCORE_{score}"
                self.logger.info(f"🛑 {trigger} for {token_mint} — score={score}")
                closed = opt.manual_close(token_mint, trigger=trigger)
                if not closed:
                    self.logger.warning(
                        f"⚠️ {trigger} manual_close failed or trade not active for {token_mint}"
                    )
                return
            if score == 2 and mc < min_mc:
                trigger = "BAD_SCORE_S2_LOWMC"
                self.logger.info(
                    f"🛑 {trigger} for {token_mint} — score=2, marketcap={mc:.0f} < {min_mc}"
                )
                closed = opt.manual_close(token_mint, trigger=trigger)
                if not closed:
                    self.logger.warning(
                        f"⚠️ {trigger} manual_close failed or trade not active for {token_mint}"
                    )
                return
            self.logger.info(
                f"✅ Post-buy checks passed for {token_mint} — score={score}, marketcap={mc:.0f}"
            )
            return

        except Exception as e:
            self.logger.error(
                f"❌ _delayed_post_buy_handler failed for {token_mint}: {e}",
                exc_info=True
            )