from services.bot_context import BotContext
from helpers.framework_utils import lamports_to_decimal
from config.dex_detection_rules import PUMPFUN_PROGRAM_IDS,RAYDIUM_PROGRAM_IDS,KNOWN_BASES,KNOWN_TOKENS
import time 

class LiquidityAnalyzer:
    def __init__(self, ctx: BotContext):
        self.ctx = ctx
        self.logger = ctx.get("logger")
        self.token_pools = {}

    def parse_liquidity_logs(self, transaction: dict, token_mint: str,pool_owner: str = None) -> dict:
        result = {
            "token_reserve": 0,
            "token_decimals": 9,
            "liquidity_breakdown": {},
            "launch_price_usd": 0,
            "pool_owner": pool_owner
        }

        meta = transaction.get("meta", {})
        for balance in meta.get("postTokenBalances", []):
            mint = balance.get("mint")
            raw_amt = balance.get("uiTokenAmount", {}).get("uiAmount")
            if raw_amt is None:
                continue
            amount = float(raw_amt)
            decimals = balance["uiTokenAmount"]["decimals"]
            owner = balance.get("owner")

            if mint == token_mint:
                result["token_reserve"] = amount
                result["token_decimals"] = decimals
            else:
                if pool_owner and owner != pool_owner:
                    continue
                if mint not in result["liquidity_breakdown"]:
                    result["liquidity_breakdown"][mint] = {"amount": 0, "decimals": decimals}
                result["liquidity_breakdown"][mint]["amount"] += amount

        return self._calculate_liquidity(token_mint, result)
    
    def _calculate_liquidity(self, token_mint: str, result: dict) -> dict:
        sol_price = 0.0
        breakdown_usd = { "SOL": 0.0, "USDC": 0.0, "USDT": 0.0, "USD1": 0.0, "OTHERS": 0.0 }
        try:
            sol_price = self.ctx.get("jupiter_client").get_sol_price()
        except Exception as e:
            self.logger.warning(f"⚠️ Failed to fetch SOL price: {e}")

        for mint, info in result["liquidity_breakdown"].items():
            amount = info["amount"]
            base_info = KNOWN_BASES.get(mint)

            if base_info:
                symbol = base_info["symbol"]
                if symbol == "SOL":
                    breakdown_usd["SOL"] += amount * sol_price
                elif symbol in {"USDC", "USDT", "USD1"}:
                    breakdown_usd[symbol] += amount
            else:
                breakdown_usd["OTHERS"] += amount

        token_amount =  result["token_reserve"]
        launch_price = 0.0
        if token_amount > 0 and breakdown_usd["SOL"] > 0:
            launch_price = self.get_current_price_on_chain(token_mint)
        token_liq_usd = token_amount * launch_price
        total_liq_usd = breakdown_usd["SOL"] + token_liq_usd
        return {
            "token_mint": token_mint,
            "token_amount": token_amount,
            "launch_price_usd": launch_price,
            "breakdown": breakdown_usd,
            "token_liq_usd": token_liq_usd,
            "total_liq_usd": total_liq_usd,
            "timestamp": time.time(),
            "pool_address": result.get("pool_owner")
        }

    def analyze_liquidty(self, transaction: dict, token_mint: str, min_liq: float) -> bool:
        pool_data = self.store_pool_mapping(token_mint, transaction)
        if not pool_data:
            return False

        pool_address, dex = pool_data

        data = self.parse_liquidity_logs(transaction, token_mint, pool_address)
        sol_liq = data["breakdown"].get("SOL", 0)
        total_liq = data["total_liq_usd"]

        if total_liq <= 0:
            self.logger.info(f"ℹ️ No liquidity info found for {token_mint}.")
            return False

        self.logger.info(
            f"💧 Liquidity detected for {token_mint} - Total ${total_liq:.2f}, "
            f"SOL side: ${sol_liq:.2f}, Token side: ${data['token_liq_usd']:.2f}, "
            f"Launch price: ${data['launch_price_usd']:.8f}"
        )
        data["pool_address"] = pool_address
        data["dex"] = dex
        self.ctx.get("pending_data")[token_mint] = data
        if sol_liq >= min_liq:
            if token_mint not in self.token_pools:
                self.token_pools[token_mint] = {"pool": pool_address, "dex": dex}

                self.logger.info(f"💾 Pool meets threshold — saving {token_mint}")
                self.logger.debug(
                    f"🔍 Pool {pool_address[:6]}... detected with {sol_liq:.2f} SOL liquidity for {token_mint}"
                )
            return True

        self.logger.info(f"⛔ Low liquidity (${sol_liq:.2f}) for {token_mint}")
        return False

    def calculate_on_chain_price(self,reserve_token: int,token_decimals: int,reserve_base: int,base_decimals: int,base_symbol: str,sol_price: float) -> float:
            token_amount = lamports_to_decimal(reserve_token, token_decimals)
            base_amount  = lamports_to_decimal(reserve_base, base_decimals)

            if token_amount == 0:
                return 0.0

            price_in_base = base_amount / token_amount

            if base_symbol == "SOL":
                return price_in_base * sol_price
            elif base_symbol in {"USDC", "USDT", "USD1"}:
                return price_in_base
            else:
                return 0.0

    def get_token_price_onchain(self, token_mint: str, pool_address: str) -> float:
        try:
            reserves = self.ctx.get("helius_client").get_token_accounts_by_owner(pool_address)
            if len(reserves) < 2:
                self.logger.warning(f"⚠️ Pool {pool_address} has insufficient reserves")
                return 0.0

            token_reserve = next((r for r in reserves if r["mint"] == token_mint), None)
            if not token_reserve:
                self.logger.warning(f"⚠️ Token mint {token_mint} not found in pool {pool_address}")
                return 0.0
            base_reserve = next((r for r in reserves if r["mint"] in KNOWN_BASES), None)
            if not base_reserve:
                self.logger.warning(f"⚠️ No known base in pool {pool_address} for {token_mint}")
                return 0.0
            base_info = KNOWN_BASES.get(base_reserve["mint"])
            if not base_info:
                self.logger.warning(f"⚠️ Unknown base mint {base_reserve['mint']} in pool {pool_address}")
                return 0.0
            
            sol_price = 1.0          
            if base_info["symbol"] == "SOL":
                sol_price = self.ctx.get("jupiter_client").get_sol_price()

            return self.calculate_on_chain_price(
                reserve_token=token_reserve["amount"],
                token_decimals=token_reserve["decimals"],
                reserve_base=base_reserve["amount"],
                base_decimals=base_reserve["decimals"],
                base_symbol=base_info["symbol"],
                sol_price=sol_price
            )

        except Exception as e:
            self.logger.error(f"❌ Failed to fetch on-chain price for {token_mint}: {e}", exc_info=True)
            return 0.0

    def get_current_price_on_chain(self, token_mint: str) -> float:
        pool_entry = self.token_pools.get(token_mint)
        if not pool_entry:
            self.logger.warning(f"⚠️ No pool stored for {token_mint}, cannot fetch price.")
            return 0.0

        pool_address = pool_entry["pool"] if isinstance(pool_entry, dict) else pool_entry
        return self.get_token_price_onchain(token_mint, pool_address)
    
    def store_pool_mapping(self, token_mint: str, transaction: dict):
        try:
            post_balances = transaction.get("meta", {}).get("postTokenBalances", [])
            account_keys = transaction.get("transaction", {}).get("message", {}).get("accountKeys", [])

            pool_address = self.detect_pool_pda(post_balances, token_mint)
            if not pool_address:
                self.logger.debug(f"⚠️ No pool detected for {token_mint}")
                return None

            if any(pid in account_keys for pid in PUMPFUN_PROGRAM_IDS):
                dex = "pumpfun"
            elif any(pid in account_keys for pid in RAYDIUM_PROGRAM_IDS):
                dex = "raydium"
            else:
                dex = "unknown"

            return pool_address, dex

        except Exception as e:
            self.logger.error(f"⚠️ Failed to detect pool for {token_mint}: {e}")
            return None, None

    def detect_pool_pda(self, post_token_balances: list[dict], token_mint: str) -> str | None:

        WSOL = KNOWN_TOKENS.get("SOL")
        candidates = []
        for bal in post_token_balances:
            mint = bal.get("mint")
            owner = bal.get("owner")
            token_info = bal.get("uiTokenAmount", {})
            raw_amount = token_info.get("amount")
            decimals = token_info.get("decimals", 0)

            if not mint or not owner or raw_amount is None:
                continue

            ui_amount = lamports_to_decimal(float(raw_amount), decimals)
            candidates.append((owner, mint, ui_amount))
        owner_balances = {}
        for owner, mint, amount in candidates:
            if owner not in owner_balances:
                owner_balances[owner] = {}
            owner_balances[owner][mint] = amount
        valid_pools = []
        for owner, balances in owner_balances.items():
            if WSOL in balances and token_mint in balances:
                total_liquidity = balances[WSOL] + balances[token_mint]
                valid_pools.append((owner, total_liquidity))
        
        if not valid_pools:
            return None

        self.logger.debug(f"token owners are {valid_pools}")
        best_owner, _ = max(valid_pools, key=lambda x: x[1])
        return best_owner

    def extract_token_mint(self,tx_data:dict) -> str:
        try:
            post_balances = tx_data.get("meta", {}).get("postTokenBalances", [])
            if post_balances:
                for b in post_balances:
                    mint = b.get("mint")
                    if mint and mint != "So11111111111111111111111111111111111111112":
                        return mint
            return None
        except Exception as e:
            self.logger.error("failed to extract new mint")
    
