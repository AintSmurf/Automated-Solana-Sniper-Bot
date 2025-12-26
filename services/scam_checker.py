from services.bot_context import BotContext

class ScamChecker:
    def __init__(self, ctx:BotContext):
        self.ctx = ctx
        self.logger = ctx.get("logger")
    
    def is_token_scam(self, response_json: dict, token_mint: str) -> bool:
        route_plan = response_json.get("routePlan") or []
        if not route_plan:
            self.logger.warning(f"🚨 No swap route for {token_mint}. Possible honeypot/illiquid.")
            return True

        swap_info = (route_plan[0] or {}).get("swapInfo") or {}

        try:
            in_amount = float(swap_info["inAmount"])
            out_amount = float(swap_info["outAmount"])
        except Exception:
            self.logger.warning(f"🚨 Missing inAmount/outAmount for {token_mint}.")
            return True

        if out_amount == 0:
            self.logger.warning(f"🚨 Zero output for {token_mint}. No liquidity.")
            return True

        # keep as a rough sanity check
        if in_amount / out_amount > 10000:
            self.logger.warning(f"⚠️ Unreasonable price ratio for {token_mint}.")
            return True

        self.logger.info(f"✅ Token {token_mint} passed quote sanity checks.")
        return False
  
    def first_phase_tests(self, token_mint: str) -> bool:
        token_amount = self.ctx.get("jupiter_client").get_solana_token_worth_in_dollars(
            self.ctx.settings["TRADE_AMOUNT"]
        )
        quote = self.ctx.get("jupiter_client").get_quote_dict(
            token_mint,
            "So11111111111111111111111111111111111111112",  # WSOL
            token_amount,
        )

        if not quote.get("quote") or not quote.get("quote_price"):
            return False

        if self.is_token_scam(quote["quote"], token_mint):
            return False
        try:
            mint_info = self.ctx.get("helius_client").get_mint_account_info(token_mint) or {}
            token_info = mint_info.get("token_info") or {}
            mint_authority = token_info.get("mint_authority")
            freeze_authority = token_info.get("freeze_authority")
            if mint_authority is not None:
                self.logger.warning(
                    f"🚨 Token {token_mint} mint authority still exists ({mint_authority}). HIGH RISK."
                )
                return False
            if freeze_authority is not None:
                self.logger.warning(
                    f"🚨 Token {token_mint} freeze authority still exists ({freeze_authority}). HIGH RISK."
                )
                return False
            if mint_info.get("mutable", False):
                if self.ctx.get("rug_check").is_liquidity_unlocked(token_mint):
                    self.logger.warning(
                        f"🚨 Token {token_mint} is mutable & liquidity is NOT locked! HIGH RISK."
                    )
                    return False
                else:
                    self.logger.info(
                        f"⚠️ Token {token_mint} is mutable but liquidity is locked. Still some risk."
                    )

            self.logger.info(f"✅ Token {token_mint} passed first-phase scam checks.")
            return True

        except Exception as e:
            self.logger.error(f"❌ Error checking scam tests for {token_mint}: {e}", exc_info=True)
            return False
 
    def second_phase_tests(self, token_mint:str,signature:str,market_cap:float, attempt:int=1):
        self.logger.info(f"⏳ Running DELAYED post-buy check (attempt {attempt}) for {token_mint}...")

        results = {
            "LP_Check": False,
            "Holders_Check": False,
            "Volume_Check": False,
            "MarketCap_Check": False,
        }
        score = 0
        # LP lock ratio
        try:
            lp_status = self.ctx.get("rug_check").is_liquidity_unlocked_test(token_mint)
            if lp_status == "safe":
                results["LP_Check"] = True
                score += 1
            elif lp_status == "risky":
                results["LP_Check"] = False
                score += 0.5
        except Exception as e:
            self.logger.error(f"❌ LP check failed for {token_mint}: {e}")

        # Holder distribution
        try:
            if self.ctx.get("helius_client").get_largest_accounts(token_mint):
                results["Holders_Check"] = True
                score += 1
        except Exception as e:
            self.logger.error(f"❌ Holder distribution check failed for {token_mint}: {e}")

        # Volume growth since launch
        try:
            self.ctx.get("volume_tracker").check_volume_growth(token_mint, signature)
            stats = self.ctx.get("volume_tracker").stats(token_mint, window=999999)
            token_id = self.ctx.get("token_dao").get_token_id_by_address(token_mint)
            self.ctx.get("volume_dao").insert_volume_snapshot(token_id, stats)
            if stats["delta_volume"] > 0:
                results["Volume_Check"] = True
                score += 1
        except Exception as e:
            self.logger.error(f"❌ Volume check failed for {token_mint}: {e}", exc_info=True)

        # Market cap
        try:
            if market_cap and market_cap <= 1_000_000:
                results["MarketCap_Check"] = True
                score += 1
        except Exception as e:
            self.logger.error(f"❌ Market cap check failed for {token_mint}: {e}")
        amount_of_holders = self.ctx.get("helius_client").get_holders_amount(token_mint)
        token_id = self.ctx.get("token_dao").get_token_id_by_address(token_mint)
        self.ctx.get("scam_checker_dao").insert_token_results(token_id,results["LP_Check"],results["Holders_Check"],results["Volume_Check"],results["MarketCap_Check"],score)
        self.ctx.get("token_dao").insert_token_stats(token_id,market_cap,amount_of_holders)
        return {"score": score, "results": results}
