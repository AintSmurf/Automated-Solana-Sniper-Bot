import pytest
from services.scam_checker import ScamChecker
from services.liquidity_analyzer import LiquidityAnalyzer
from config.dex_detection_rules import PUMPFUN_PROGRAM_IDS


class DummyLogger:
    def info(self, msg): pass
    def warning(self, msg): pass
    def error(self, msg, exc_info=False): pass
    def debug(self, msg): pass

class UnitCtx:
    def __init__(self, settings=None):
        self.settings = settings or {
            "SIM_MODE": True,
            "NETWORK": "devnet",
            "TRADE_AMOUNT": 5,
        }
        self._services = {}

    def register(self, key, value):
        self._services[key] = value

    def get(self, key, default=None):
        return self._services.get(key, default)

class FakeJupiterClient:
    def __init__(self, quote_result=None, token_amount=123456, sol_price=200):
        self.quote_result = quote_result or {
            "quote": {
                "routePlan": [
                    {"swapInfo": {"inAmount": "1000000", "outAmount": "500"}}
                ]
            },
            "quote_price": 0.123,
        }
        self.token_amount = token_amount
        self.sol_price = sol_price

    def get_solana_token_worth_in_dollars(self, trade_amount):
        return self.token_amount

    def get_quote_dict(self, token_mint, wsol, token_amount):
        return self.quote_result
    
    def get_sol_price(self):
        return self.sol_price

class FakeHeliusClient:
    def __init__(self, mint_info=None, largest_accounts_ok=False, holders_count=0):
        self.mint_info = mint_info or {
            "authorities": [],
            "frozen": False,
            "mutable": False,
            "token_info": {},
        }
        self.largest_accounts_ok = largest_accounts_ok
        self.holders_count = holders_count

    def get_mint_account_info(self, token_mint):
        return self.mint_info

    def get_largest_accounts(self, token_mint):
        return self.largest_accounts_ok

    def get_holders_amount(self, token_mint):
        return self.holders_count

class FakeRugCheck:
    def __init__(self, liquidity_unlocked=False, lp_status="unknown"):
        self.liquidity_unlocked = liquidity_unlocked
        self.lp_status = lp_status

    def is_liquidity_unlocked(self, token_mint):
        return self.liquidity_unlocked

    def is_liquidity_unlocked_test(self, token_mint):
        return self.lp_status

class FakeVolumeTracker:
    def __init__(self, delta_volume=0):
        self.delta_volume = delta_volume

    def check_volume_growth(self, token_mint, signature):
        return None

    def stats(self, token_mint, window=999999):
        return {"delta_volume": self.delta_volume}

@pytest.fixture
def ctx_unit():
    return UnitCtx()

@pytest.fixture
def scam_checker(ctx_unit):
    ctx_unit.register("logger", DummyLogger())
    return ScamChecker(ctx_unit)

@pytest.fixture
def scam_checker_with_deps(ctx_unit):
    ctx_unit.register("logger", DummyLogger())
    ctx_unit.register("jupiter_client", FakeJupiterClient())
    ctx_unit.register("helius_client", FakeHeliusClient())
    ctx_unit.register("rug_check", FakeRugCheck())
    ctx_unit.register("volume_tracker", FakeVolumeTracker())
    return ScamChecker(ctx_unit)

@pytest.fixture
def liquidity_analyzer(ctx_unit):
    ctx_unit.register("logger", DummyLogger())
    ctx_unit.register("jupiter_client", FakeJupiterClient())
    return LiquidityAnalyzer(ctx_unit)

@pytest.fixture
def tx_liquidity_sample():
    return {
        "transaction": {
            "message": {
                "accountKeys": ["some_wallet", "some_other_key"]
            }
        },
        "meta": {
            "loadedAddresses": {
                "writable": [],
                "readonly": [PUMPFUN_PROGRAM_IDS[0]],
            },
            "postTokenBalances": [
                {
                    "mint": "So11111111111111111111111111111111111111112",
                    "owner": "pool_owner_1",
                    "uiTokenAmount": {"amount": "136157084676", "decimals": 9, "uiAmount": 136.157084676},
                },
                {
                    "mint": "mint123",
                    "owner": "pool_owner_1",
                    "uiTokenAmount": {"amount": "135137758373139", "decimals": 6, "uiAmount": 135137758.373139},
                },
            ],
        },
    }