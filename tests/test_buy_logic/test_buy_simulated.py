import pytest
from unittest.mock import MagicMock
from datetime import datetime


from helpers.solana_manager import SolanaManager  

class DummyRateLimiter:
    def wait(self):
        pass

@pytest.mark.solana_manager
@pytest.mark.tcid1
def test_buy_simulated_does_not_execute_transaction():
    # Arrange
    rate_limiter = DummyRateLimiter()
    solana_manager = SolanaManager(rate_limiter)
    solana_manager.get_solana_token_worth_in_dollars = MagicMock(return_value=10_000_000)
    solana_manager.get_quote = MagicMock(return_value={
        'inAmount': '10000000',
        'outAmount': '50000000'
    })
    solana_manager.get_token_decimals = MagicMock(return_value=9)
    solana_manager.add_token_account = MagicMock()
    solana_manager.get_sol_price = MagicMock(return_value=20)
    solana_manager.get_account_balances = MagicMock(return_value=[])

    mock_excel_utility = MagicMock()
    solana_manager.excel_utility = mock_excel_utility

    # Act
    result = solana_manager.buy(
        input_mint="So11111111111111111111111111111111111111112",
        output_mint="TestMint",
        usd_amount=10,
        sim=True
    )

    # Assert
    assert result == "SIMULATED"
    mock_excel_utility.save_to_csv.assert_called()
    solana_manager.add_token_account.assert_not_called()

@pytest.mark.solana_manager
@pytest.mark.tcid2
def test_buy_simulated_zero_tokens():
    rate_limiter = DummyRateLimiter()
    solana_manager = SolanaManager(rate_limiter)
    solana_manager.get_solana_token_worth_in_dollars = MagicMock(return_value=10_000_000)
    solana_manager.get_quote = MagicMock(return_value={
        'inAmount': '10000000',
        'outAmount': '0'
    })
    solana_manager.get_token_decimals = MagicMock(return_value=9)
    solana_manager.excel_utility = MagicMock()

    result = solana_manager.buy(
        input_mint="So11111111111111111111111111111111111111112",
        output_mint="TestMint",
        usd_amount=10,
        sim=True
    )

    assert result is None
    solana_manager.excel_utility.save_to_csv.assert_not_called()
