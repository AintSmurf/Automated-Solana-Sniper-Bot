import pytest

@pytest.mark.unit
@pytest.mark.liquidity_service
def test_calculate_on_chain_price_sol_base(liquidity_analyzer):
    price = liquidity_analyzer.calculate_on_chain_price(
        reserve_token=1_000_000,
        token_decimals=6,
        reserve_base=2_000_000_000, 
        base_decimals=9,
        base_symbol="SOL",
        sol_price=100,
    )

    assert price == 200.0

@pytest.mark.unit
@pytest.mark.liquidity_service
def test_calculate_on_chain_price_usdc_base(liquidity_analyzer):
    price = liquidity_analyzer.calculate_on_chain_price(
        reserve_token=2_000_000,
        token_decimals=6,
        reserve_base=10_000_000,
        base_decimals=6,
        base_symbol="USDC",
        sol_price=100,
    )

    assert price == 5.0

@pytest.mark.unit
@pytest.mark.liquidity_service
def test_calculate_on_chain_price_zero_token_amount(liquidity_analyzer):
    price = liquidity_analyzer.calculate_on_chain_price(
        reserve_token=0,
        token_decimals=6,
        reserve_base=10_000_000,
        base_decimals=6,
        base_symbol="USDC",
        sol_price=100,
    )

    assert price == 0.0

@pytest.mark.unit
@pytest.mark.liquidity_service
def test_calculate_on_chain_price_unknown_base_returns_zero(liquidity_analyzer):
    price = liquidity_analyzer.calculate_on_chain_price(
        reserve_token=1_000_000,
        token_decimals=6,
        reserve_base=10_000_000,
        base_decimals=6,
        base_symbol="UNKNOWN",
        sol_price=100,
    )

    assert price == 0.0

@pytest.mark.unit
@pytest.mark.liquidity_service
def test_extract_token_mint_returns_first_non_wsol(liquidity_analyzer):
    tx_data = {
        "meta": {
            "postTokenBalances": [
                {"mint": "So11111111111111111111111111111111111111112"},
                {"mint": "mint123"},
            ]
        }
    }

    assert liquidity_analyzer.extract_token_mint(tx_data) == "mint123"

@pytest.mark.unit
@pytest.mark.liquidity_service
def test_extract_token_mint_returns_none_when_only_wsol(liquidity_analyzer):
    tx_data = {
        "meta": {
            "postTokenBalances": [
                {"mint": "So11111111111111111111111111111111111111112"},
            ]
        }
    }

    assert liquidity_analyzer.extract_token_mint(tx_data) is None

@pytest.mark.unit
@pytest.mark.liquidity_service
def test_extract_token_mint_returns_none_when_no_balances(liquidity_analyzer):
    tx_data = {"meta": {"postTokenBalances": []}}

    assert liquidity_analyzer.extract_token_mint(tx_data) is None

@pytest.mark.unit
@pytest.mark.liquidity_service
def test_detect_pool_pda_returns_best_owner(liquidity_analyzer):
    balances = [
        {
            "mint": "So11111111111111111111111111111111111111112",
            "owner": "owner1",
            "uiTokenAmount": {"amount": "1000000000", "decimals": 9},
        },
        {
            "mint": "mint123",
            "owner": "owner1",
            "uiTokenAmount": {"amount": "5000000", "decimals": 6},
        },
        {
            "mint": "So11111111111111111111111111111111111111112",
            "owner": "owner2",
            "uiTokenAmount": {"amount": "2000000000", "decimals": 9},
        },
        {
            "mint": "mint123",
            "owner": "owner2",
            "uiTokenAmount": {"amount": "9000000", "decimals": 6},
        },
    ]

    assert liquidity_analyzer.detect_pool_pda(balances, "mint123") == "owner2"

@pytest.mark.unit
@pytest.mark.liquidity_service
def test_detect_pool_pda_returns_none_when_no_valid_pool(liquidity_analyzer):
    balances = [
        {
            "mint": "mint123",
            "owner": "owner1",
            "uiTokenAmount": {"amount": "5000000", "decimals": 6},
        }
    ]

    assert liquidity_analyzer.detect_pool_pda(balances, "mint123") is None

@pytest.mark.unit
@pytest.mark.liquidity_service
def test_store_pool_mapping_detects_pumpfun_from_loaded_addresses(liquidity_analyzer, tx_liquidity_sample):
    assert liquidity_analyzer.store_pool_mapping("mint123", tx_liquidity_sample) == ("pool_owner_1", "pumpfun")

@pytest.mark.unit
@pytest.mark.liquidity_service
def test_store_pool_mapping_returns_none_when_no_pool(liquidity_analyzer, tx_liquidity_sample):
    tx_liquidity_sample["meta"]["postTokenBalances"] = []
    assert liquidity_analyzer.store_pool_mapping("mint123", tx_liquidity_sample) is None

@pytest.mark.unit
@pytest.mark.liquidity_service
def test_parse_liquidity_logs_parses_realistic_post_token_balances(liquidity_analyzer, tx_liquidity_sample):
    liquidity_analyzer.ctx.get("jupiter_client").sol_price = 200
    liquidity_analyzer.get_current_price_on_chain = lambda token_mint: 0.5
    out = liquidity_analyzer.parse_liquidity_logs(tx_liquidity_sample, "mint123", "pool_owner_1")
    assert out["token_mint"] == "mint123"
    assert out["token_amount"] == 135137758.373139
    assert out["breakdown"]["SOL"] == 136.157084676 * 200
    assert out["launch_price_usd"] == 0.5
    assert out["pool_address"] == "pool_owner_1"

@pytest.mark.unit
@pytest.mark.liquidity_service
def test_parse_liquidity_logs_filters_non_pool_owner_base_balances(liquidity_analyzer, tx_liquidity_sample):
    liquidity_analyzer.ctx.get("jupiter_client").sol_price = 100
    liquidity_analyzer.get_current_price_on_chain = lambda token_mint: 1.0

    tx_liquidity_sample["meta"]["postTokenBalances"].append(
        {
            "mint": "So11111111111111111111111111111111111111112",
            "owner": "other_owner",
            "uiTokenAmount": {
                "amount": "50000000000",
                "decimals": 9,
                "uiAmount": 50,
            },
        }
    )

    out = liquidity_analyzer.parse_liquidity_logs(tx_liquidity_sample, "mint123", "pool_owner_1")

    assert out["breakdown"]["SOL"] == 136.157084676 * 100

@pytest.mark.unit
@pytest.mark.liquidity_service
def test_calculate_liquidity_with_sol_and_token_side(liquidity_analyzer):
    liquidity_analyzer.ctx.get("jupiter_client").sol_price = 200
    liquidity_analyzer.get_current_price_on_chain = lambda token_mint: 0.5

    result = {
        "token_reserve": 1000,
        "token_decimals": 6,
        "liquidity_breakdown": {
            "So11111111111111111111111111111111111111112": {"amount": 2, "decimals": 9}
        },
        "pool_owner": "pool1",
    }

    out = liquidity_analyzer._calculate_liquidity("mint123", result)

    assert out["token_mint"] == "mint123"
    assert out["token_amount"] == 1000
    assert out["launch_price_usd"] == 0.5
    assert out["breakdown"]["SOL"] == 400
    assert out["token_liq_usd"] == 500
    assert out["total_liq_usd"] == 900
    assert out["pool_address"] == "pool1"

@pytest.mark.unit
@pytest.mark.liquidity_service
def test_calculate_liquidity_stablecoin_side_counts_directly(liquidity_analyzer):
    liquidity_analyzer.ctx.get("jupiter_client").sol_price = 200
    liquidity_analyzer.get_current_price_on_chain = lambda token_mint: 0.0

    result = {
        "token_reserve": 0,
        "token_decimals": 6,
        "liquidity_breakdown": {
            "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v": {"amount": 1500, "decimals": 6}
        },
        "pool_owner": "pool2",
    }

    out = liquidity_analyzer._calculate_liquidity("mint123", result)

    assert out["breakdown"]["USDC"] == 1500
    assert out["token_liq_usd"] == 0
    assert out["total_liq_usd"] == 1500

@pytest.mark.unit
@pytest.mark.liquidity_service
def test_calculate_liquidity_unknown_base_goes_to_others(liquidity_analyzer):
    liquidity_analyzer.ctx.get("jupiter_client").sol_price = 200
    liquidity_analyzer.get_current_price_on_chain = lambda token_mint: 0.0

    result = {
        "token_reserve": 0,
        "token_decimals": 6,
        "liquidity_breakdown": {
            "unknown_mint": {"amount": 321, "decimals": 6}
        },
        "pool_owner": "pool3",
    }

    out = liquidity_analyzer._calculate_liquidity("mint123", result)

    assert out["breakdown"]["OTHERS"] == 321
    assert out["total_liq_usd"] == 0

@pytest.mark.unit
@pytest.mark.liquidity_service
def test_calculate_liquidity_without_token_or_sol_keeps_launch_price_zero(liquidity_analyzer):
    liquidity_analyzer.ctx.get("jupiter_client").sol_price = 200
    liquidity_analyzer.get_current_price_on_chain = lambda token_mint: 999
    result = {
        "token_reserve": 0,
        "token_decimals": 6,
        "liquidity_breakdown": {},
        "pool_owner": "pool4",
    }
    out = liquidity_analyzer._calculate_liquidity("mint123", result)
    assert out["launch_price_usd"] == 0.0
    assert out["token_liq_usd"] == 0.0
    assert out["total_liq_usd"] == 0.0