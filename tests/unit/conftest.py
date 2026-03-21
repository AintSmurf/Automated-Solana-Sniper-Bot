import pytest
from services.scam_checker import ScamChecker
from services.liquidity_analyzer import LiquidityAnalyzer
from config.dex_detection_rules import PUMPFUN_PROGRAM_IDS
from core.trade_manager import TraderManager





class DummyLogger:
    def __init__(self):
        self.infos = []
        self.warnings = []
        self.errors = []
        self.debugs = []

    def info(self, msg): self.infos.append(msg)
    def warning(self, msg): self.warnings.append(msg)
    def error(self, msg, exc_info=False): self.errors.append(msg)
    def debug(self, msg): self.debugs.append(msg)

class DummySettingsManager:
    def get_notification_settings(self):
        return {
            "DISCORD": {
                "LIVE_CHANNEL": "test-channel"
            }
        }

class UnitCtx:
    def __init__(self, settings=None):
        self.settings = settings or {
            "SIM_MODE": True,
            "NETWORK": "devnet",
            "TRADE_AMOUNT": 5,
            "USE_SENDER": {
                "BUY": False,
                "SELL": False,
            },
        }
        self._services = {}
        self.settings_manager = DummySettingsManager()

    def register(self, key, value):
        self._services[key] = value

    def get(self, key, default=None):
        return self._services.get(key, default)

class FakeJupiterClient:
    def __init__(self, quote_result=None, token_amount=123456, sol_price=200, swap_tx="tx64"):
        self.quote_result = quote_result or {
            "quote": {"routePlan": []},
            "outAmount": 5000,
            "entry_usd": 0.123,
        }
        self.token_amount = token_amount
        self.sol_price = sol_price
        self.swap_tx = swap_tx

    def get_solana_token_worth_in_dollars(self, trade_amount):
        return self.token_amount

    def get_quote_dict(self, *args, **kwargs):
        return self.quote_result

    def get_sol_price(self):
        return self.sol_price

    def get_swap_transaction(self, quote):
        return self.swap_tx

    def get_swap_transaction_for_sender(self, quote):
        return f"sender-{self.swap_tx}"

class FakeHeliusClient:
    def __init__(self,mint_info=None,largest_accounts_ok=False,holders_count=0,send_sig="sig-123",verify_result="confirmed",decimals=6):
        self.mint_info = mint_info or {
            "authorities": [],
            "frozen": False,
            "mutable": False,
            "token_info": {},
        }
        self.largest_accounts_ok = largest_accounts_ok
        self.holders_count = holders_count
        self.send_sig = send_sig
        self.verify_result = verify_result
        self.decimals = decimals

        self.sent_transactions = []
        self.sent_sender_transactions = []

    def get_mint_account_info(self, token_mint):
        return self.mint_info

    def get_largest_accounts(self, token_mint):
        return self.largest_accounts_ok

    def get_holders_amount(self, token_mint):
        return self.holders_count

    def send_transaction(self, txn_64):
        self.sent_transactions.append(txn_64)
        return self.send_sig

    def send_via_sender(self, txn_64):
        self.sent_sender_transactions.append(txn_64)
        return self.send_sig

    def verify_signature(self, signature):
        return self.verify_result

    def get_token_decimals(self, token_mint):
        return self.decimals

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

class FakeFuture:
    def __init__(self, result_value=None, done_state=False, exception=None):
        self.result_value = result_value
        self.done_state = done_state
        self.exception = exception
        self.callbacks = []

    def result(self, timeout=None):
        if self.exception:
            raise self.exception
        return self.result_value

    def done(self):
        return self.done_state

    def add_done_callback(self, cb):
        self.callbacks.append(cb)

    def fire(self):
        for cb in self.callbacks:
            cb(self)

class FakeWalletClient:
    def __init__(self, token_balances=None, account_balances=None, token_exists=False):
        self.token_balances = token_balances or []
        self.account_balances = account_balances or []
        self.token_exists = token_exists

    def get_token_balances(self):
        return self.token_balances

    def get_account_balances(self):
        return self.account_balances

    def check_if_token_exists_in_wallet(self, token_mint):
        return self.token_exists

class FakeTradeLifecycleService:
    def __init__(self):
        self.simulated_calls = []
        self.submitted_buys = []
        self.submitted_sells = []
        self.buy_status_calls = []
        self.buy_fail_calls = []
        self.sell_status_calls = []
        self.sell_fail_calls = []

    def insert_simulated_trade(self, token_mint, entry_price_usd, current_price_usd):
        self.simulated_calls.append((token_mint, entry_price_usd, current_price_usd))
        return "sim-trade-id"

    def insert_submitted_buy(self, data, signature, output_mint):
        self.submitted_buys.append((data, signature, output_mint))

    def mark_sell_submitted(self, token_mint, signature, trigger_reason=None):
        self.submitted_sells.append((token_mint, signature, trigger_reason))

    def on_buy_status(self, signature, payload, status):
        self.buy_status_calls.append((signature, payload, status))

    def on_buy_fail_or_timeout(self, signature, payload, status):
        self.buy_fail_calls.append((signature, payload, status))

    def on_sell_status(self, signature, payload, status):
        self.sell_status_calls.append((signature, payload, status))

    def on_sell_fail_or_timeout(self, signature, payload, status):
        self.sell_fail_calls.append((signature, payload, status))

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
    ctx_unit.register("pending_data", {})
    return LiquidityAnalyzer(ctx_unit)

@pytest.fixture
def trader_manager(trader_ctx):
    return TraderManager(trader_ctx)

@pytest.fixture
def trader_ctx(ctx_unit):
    ctx_unit.register("logger", DummyLogger())
    ctx_unit.register("tracker_logger", DummyLogger())
    ctx_unit.register("jupiter_client", FakeJupiterClient())
    ctx_unit.register("helius_client", FakeHeliusClient())
    ctx_unit.register("trade_lifecycle_service", FakeTradeLifecycleService())
    ctx_unit.register("wallet_client", FakeWalletClient())
    return ctx_unit

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
