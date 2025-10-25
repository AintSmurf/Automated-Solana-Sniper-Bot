from services.bot_context import BotContext

class ScamChecker:
    def __init__(self, ctx:BotContext):
        self.ctx = ctx
        self.logger = ctx.get("logger")
    
    def is_token_scam(self, response_json:dict, token_mint:str) -> bool:
        if "routePlan" not in response_json or not response_json["routePlan"]:
            self.logger.warning(f"🚨 No swap route for {token_mint}. Possible honeypot.")
            return True

        best_route = response_json["routePlan"][0]["swapInfo"]
        in_amount = float(best_route["inAmount"])
        out_amount = float(best_route["outAmount"])
        fee_amount = float(best_route["feeAmount"])

        fee_ratio = fee_amount / in_amount if in_amount > 0 else 0
        if fee_ratio > 0.05:
            self.logger.warning(
                f"⚠️ High tax detected ({fee_ratio * 100}%). Possible scam token."
            )
            return True

        self.logger.info("token scam test - tax check passed")

        if out_amount == 0:
            self.logger.warning(
                f"🚨 Token has zero output in swap! No liquidity detected for {token_mint}."
            )
            return True

        self.logger.info("token scam test - output check passed")

        if in_amount / out_amount > 10000:
            self.logger.warning(
                f"⚠️ Unreasonable token price ratio for {token_mint}. Possible rug."
            )
            return True

        self.logger.info("token scam test - price ratio check passed")
        self.logger.info(f"✅ Token {token_mint} passed Jupiter scam detection.")
        return False    
    
    def first_phase_tests(self, token_mint: str) -> bool:
        token_amount = self.ctx.get("jupiter_client").get_solana_token_worth_in_dollars(15)
        quote = self.ctx.get("jupiter_client").get_quote_dict(
            token_mint, "So11111111111111111111111111111111111111112", token_amount
        )

        if not quote.get("quote") or not quote.get("quote_price"):
            return False

        if self.is_token_scam(quote.get("quote"), token_mint):
            return False

        try:
            mint_info = self.ctx.get("helius_client").get_mint_account_info(token_mint)

            if not mint_info.get("authorities") or mint_info["authorities"][0].get("address") != "TSLvdd1pWpHVjahSpsvCXUbgwsL3JAcvokwaKt1eokM":
                self.logger.warning(
                    f"🚨 Token {token_mint} still has FULL authority! Devs can mint or change supply. HIGH RISK."
                )
                return False

            if mint_info.get("frozen", False):
                self.logger.warning(
                    f"🚨 Token {token_mint} has freeze authority! Devs can freeze wallets. HIGH RISK."
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
            else:
                results["Volume_Check"] = f"FAIL (ΔVol ${stats['delta_volume']:.2f})"
        except Exception as e:
            self.logger.error(f"❌ Volume check failed for {token_mint}: {e}", exc_info=True)

        # Market cap
        try:
            if market_cap and market_cap <= 1_000_000:
                results["MarketCap_Check"] = True
                score += 1
        except Exception as e:
            self.logger.error(f"❌ Market cap check failed for {token_mint}: {e}")
        token_id = self.ctx.get("token_dao").get_token_id_by_address(token_mint)
        self.ctx.get("scam_checker_dao").insert_token_results(token_id,results["LP_Check"],results["Holders_Check"],results["Volume_Check"],results["MarketCap_Check"],score)
        return {"score": score, "results": results}
    