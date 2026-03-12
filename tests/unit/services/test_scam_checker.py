import pytest

@pytest.mark.unit
@pytest.mark.scam_service
def test_is_token_scam_route_plan_missing(scam_checker):
    response_json = {}
    assert scam_checker.is_token_scam(response_json, "mint123") is True

@pytest.mark.unit
@pytest.mark.scam_service
def test_is_token_scam_missing_amounts(scam_checker):
    response_json = {
        "routePlan": [
            {"swapInfo": {}}
        ]
    }
    assert scam_checker.is_token_scam(response_json, "mint123") is True

@pytest.mark.unit
@pytest.mark.scam_service
def test_is_token_scam_zero_out_amount(scam_checker):
    response_json = {
        "routePlan": [
            {"swapInfo": {"inAmount": "1000000", "outAmount": "0"}}
        ]
    }

    assert scam_checker.is_token_scam(response_json, "mint123") is True

@pytest.mark.unit
@pytest.mark.scam_service
def test_is_token_scam_valid_quote(scam_checker):
    response_json = {
        "routePlan": [
            {"swapInfo": {"inAmount": "1000000", "outAmount": "500"}}
        ]
    }
    assert scam_checker.is_token_scam(response_json, "mint123") is False

@pytest.mark.unit
@pytest.mark.scam_service
def test_first_phase_tests_frozen_token_returns_false(scam_checker_with_deps):
    scam_checker_with_deps.ctx.get("helius_client").mint_info["frozen"] = True
    assert scam_checker_with_deps.first_phase_tests("mint123") is False

@pytest.mark.unit
@pytest.mark.scam_service
def test_first_phase_tests_quote_missing_returns_false(scam_checker_with_deps):
    scam_checker_with_deps.ctx.get("jupiter_client").quote_result = {
        "quote": None,
        "quote_price": None,
    }
    assert scam_checker_with_deps.first_phase_tests("mint123") is False

@pytest.mark.unit
@pytest.mark.scam_service
def test_first_phase_tests_authorities_only_returns_true(scam_checker_with_deps):
    scam_checker_with_deps.ctx.get("helius_client").mint_info["authorities"] = [{"address": "abc", "scopes": ["full"]}]
    assert scam_checker_with_deps.first_phase_tests("mint123") is True

@pytest.mark.unit
@pytest.mark.scam_service
def test_first_phase_tests_mutable_returns_false(scam_checker_with_deps):
    scam_checker_with_deps.ctx.get("helius_client").mint_info["mutable"] = True
    scam_checker_with_deps.ctx.get("rug_check").liquidity_unlocked = True
    assert scam_checker_with_deps.first_phase_tests("mint123") is False

@pytest.mark.unit
@pytest.mark.scam_service
def test_first_phase_tests_mutable_and_locked_returns_true(scam_checker_with_deps):
    scam_checker_with_deps.ctx.get("helius_client").mint_info["mutable"] = True
    scam_checker_with_deps.ctx.get("rug_check").liquidity_unlocked = False

    assert scam_checker_with_deps.first_phase_tests("mint123") is True

@pytest.mark.unit
@pytest.mark.scam_service
def test_second_phase_tests_all_good_returns_score_4(scam_checker_with_deps):
    scam_checker_with_deps.ctx.get("rug_check").lp_status = "safe"
    scam_checker_with_deps.ctx.get("helius_client").largest_accounts_ok = True
    scam_checker_with_deps.ctx.get("helius_client").holders_count = 120
    scam_checker_with_deps.ctx.get("volume_tracker").delta_volume = 5000

    res = scam_checker_with_deps.second_phase_tests("mint123", "sig123", 500_000)

    assert res["score"] == 4
    assert res["results"]["LP_Check"] is True
    assert res["results"]["Holders_Check"] is True
    assert res["results"]["Volume_Check"] is True
    assert res["results"]["MarketCap_Check"] is True
    assert res["holders_count"] == 120

@pytest.mark.unit
@pytest.mark.scam_service
def test_second_phase_tests_risky_lp_gives_half_point(scam_checker_with_deps):
    scam_checker_with_deps.ctx.get("rug_check").lp_status = "risky"
    scam_checker_with_deps.ctx.get("helius_client").largest_accounts_ok = False
    scam_checker_with_deps.ctx.get("helius_client").holders_count = 10
    scam_checker_with_deps.ctx.get("volume_tracker").delta_volume = 0

    res = scam_checker_with_deps.second_phase_tests("mint123", "sig123", 2_000_000)

    assert res["score"] == 0.5
    assert res["results"]["LP_Check"] is False
    assert res["results"]["Holders_Check"] is False
    assert res["results"]["Volume_Check"] is False
    assert res["results"]["MarketCap_Check"] is False

@pytest.mark.unit
@pytest.mark.scam_service
def test_second_phase_tests_positive_volume_sets_volume_check(scam_checker_with_deps):
    scam_checker_with_deps.ctx.get("rug_check").lp_status = "unknown"
    scam_checker_with_deps.ctx.get("helius_client").largest_accounts_ok = False
    scam_checker_with_deps.ctx.get("helius_client").holders_count = 55
    scam_checker_with_deps.ctx.get("volume_tracker").delta_volume = 1

    res = scam_checker_with_deps.second_phase_tests("mint123", "sig123", 2_000_000)

    assert res["score"] == 1
    assert res["results"]["Volume_Check"] is True

@pytest.mark.unit
@pytest.mark.scam_service
def test_second_phase_tests_market_cap_under_limit_sets_check(scam_checker_with_deps):
    scam_checker_with_deps.ctx.get("rug_check").lp_status = "unknown"
    scam_checker_with_deps.ctx.get("helius_client").largest_accounts_ok = False
    scam_checker_with_deps.ctx.get("helius_client").holders_count = 40
    scam_checker_with_deps.ctx.get("volume_tracker").delta_volume = 0

    res = scam_checker_with_deps.second_phase_tests("mint123", "sig123", 999_999)

    assert res["score"] == 1
    assert res["results"]["MarketCap_Check"] is True

@pytest.mark.unit
@pytest.mark.scam_service
def test_second_phase_tests_holder_check_sets_score(scam_checker_with_deps):
    scam_checker_with_deps.ctx.get("rug_check").lp_status = "unknown"
    scam_checker_with_deps.ctx.get("helius_client").largest_accounts_ok = True
    scam_checker_with_deps.ctx.get("helius_client").holders_count = 88
    scam_checker_with_deps.ctx.get("volume_tracker").delta_volume = 0

    res = scam_checker_with_deps.second_phase_tests("mint123", "sig123", 2_000_000)

    assert res["score"] == 1
    assert res["results"]["Holders_Check"] is True
    assert res["holders_count"] == 88