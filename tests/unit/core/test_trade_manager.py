import pytest
from tests.unit.conftest import FakeFuture, FakeWalletClient



@pytest.mark.unit
@pytest.mark.trade_manager
def test_buy_simulated_does_not_submit_real_trade(trader_ctx,trader_manager):

    helius = trader_ctx.get("helius_client")
    lifecycle = trader_ctx.get("trade_lifecycle_service")

    result = trader_manager.buy("USDC", "TOKEN1", 5, sim=True)

    assert result == "sim-trade-id"
    assert len(lifecycle.simulated_calls) == 1
    assert lifecycle.submitted_buys == []
    assert helius.sent_transactions == []
    assert helius.sent_sender_transactions == []
    assert trader_manager.pending_futures == {}

@pytest.mark.unit
@pytest.mark.trade_manager
def test_buy_returns_none_when_quote_missing(trader_ctx,trader_manager):
    trader_ctx.get("jupiter_client").quote_result = None

    result = trader_manager.buy("USDC", "TOKEN1", 5, sim=False)

    lifecycle = trader_ctx.get("trade_lifecycle_service")
    assert result is None
    assert lifecycle.submitted_buys == []
    assert trader_manager.pending_futures == {}

@pytest.mark.unit
@pytest.mark.trade_manager
def test_buy_real_submits_and_tracks_future(monkeypatch, trader_ctx,trader_manager):
    fake_future = FakeFuture(result_value="confirmed", done_state=False)

    monkeypatch.setattr(
        "core.trade_manager.run_bg",
        lambda fn, sig: fake_future,
    )

    result = trader_manager.buy("USDC", "TOKEN1", 5, sim=False)

    lifecycle = trader_ctx.get("trade_lifecycle_service")
    helius = trader_ctx.get("helius_client")

    assert result == "sig-123"
    assert len(helius.sent_transactions) == 1
    assert len(lifecycle.submitted_buys) == 1
    assert "TOKEN1" in trader_manager.pending_futures
    assert len(fake_future.callbacks) == 1

@pytest.mark.unit
@pytest.mark.trade_manager
def test_sell_returns_none_when_wallet_has_no_token(trader_ctx,trader_manager):
    trader_ctx.register("wallet_client", FakeWalletClient(token_balances=[]))

    result = trader_manager.sell("TOKEN1", "USDC")

    lifecycle = trader_ctx.get("trade_lifecycle_service")
    assert result is None
    assert lifecycle.submitted_sells == []
    assert trader_manager.pending_futures == {}

@pytest.mark.unit
@pytest.mark.trade_manager
def test_buy_callback_failed_clears_pending(trader_ctx,trader_manager):
    trader_manager.pending_futures["TOKEN1"] = object()

    payload = {
        "output_mint": "TOKEN1",
        "entry_price_usd": 0.25,
        "usd_spent": 5,
    }

    callback = trader_manager._signature_status_callback("sig-123", "buy", payload)
    callback(FakeFuture(result_value="failed"))

    lifecycle = trader_ctx.get("trade_lifecycle_service")
    assert lifecycle.buy_fail_calls == [("sig-123", payload, "failed")]
    assert "TOKEN1" not in trader_manager.pending_futures

@pytest.mark.unit
@pytest.mark.trade_manager
def test_sell_callback_confirmed_but_token_still_exists_keeps_open(trader_ctx,trader_manager):
    trader_ctx.register("wallet_client", FakeWalletClient(token_exists=True))
    trader_manager.pending_futures["TOKEN1"] = object()

    payload = {"token_mint": "TOKEN1", "trigger_reason": "tp"}

    callback = trader_manager._signature_status_callback("sig-sell", "sell", payload)
    callback(FakeFuture(result_value="confirmed"))

    lifecycle = trader_ctx.get("trade_lifecycle_service")
    assert lifecycle.sell_status_calls == []
    assert "TOKEN1" in trader_manager.pending_futures