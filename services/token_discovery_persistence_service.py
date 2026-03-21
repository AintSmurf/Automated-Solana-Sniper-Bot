from services.bot_context import BotContext


class TokenDiscoveryPersistenceService:
    
    def __init__(self, ctx: BotContext):
        self.ctx = ctx
        self.logger = ctx.get("logger")

    def persist_discovered_token(self, signature: str, token_mint: str):
        pending = self.ctx.get("pending_data").pop(token_mint, None)
        if not pending:
            return None

        try:
            token_id = self.ctx.get("token_dao").insert_new_token(signature, token_mint)

            pool_addr = pending.get("pool_address")
            dex = pending.get("dex")
            if pool_addr and dex:
                self.ctx.get("liquidity_dao").insert_pool(token_id, pool_addr, dex)

            liq_id = self.ctx.get("liquidity_dao").insert_snapshot(token_id, pending)
            return liq_id

        except Exception as db_err:
            self.logger.error(f"💾 DB insert failed for {token_mint}: {db_err}", exc_info=True)
            return None