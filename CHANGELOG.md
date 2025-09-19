# Changelog

All notable changes to this project will be documented in this file.  

---

## [3.0.0]

### Added
- **LiquidityAnalyzer** — dedicated class for:
  - Parsing post-token balances from transactions.
  - Converting lamports to decimals.
  - Calculating liquidity (USD) and launch price.
  - Detecting pool PDA owners with largest WSOL+token reserves.
  - Storing pool mappings (Pump.fun / Raydium) with migration detection.
  - On-chain price lookups from pool reserves.
- **KNOWN_TOKENS** — mapping of symbols → mints for quick lookups.
- **KNOWN_BASES** — mapping of mint → {symbol, decimals} for consistent base handling.
- **Excel utilities**:
  - `build_pda_excel()` and `save_pool_pda()` for structured logging of pool mappings.
  - `update_buy()` / `update_sell()` to update entry/exit prices in CSVs.
- **Unified conversion helpers**:
  - `lamports_to_decimal(amount, decimals)` and `decimal_to_lamports(amount, decimals)`.

### Changed
- **SolanaManager** refactored into a **facade** delegating tasks to helpers.
- **TraderManager**:
  - `_signature_finalize_callback` now only verifies signature finalization.
  - Entry/exit updates moved into:
    - `_update_entry_price_with_balance()` — sets real entry price after buy.
    - `_update_exit_with_balance()` — sets exit USD and PnL after sell.
- **Sell flow**:
  - Exit USD and PnL updated in Excel via `update_sell()` + `save_closed_position()`.
  - No longer handled inside `finalize_trade`.
- **Simulation mode**:
  - Simulation sell exits handled in `OpenPositionTracker` (skips real transaction).
  - TraderManager no longer branches logic for sim vs real inside finalize flow.
- **BotContext** extended:
  - Provides `helius_client`, `jupiter_client`, and `excel_utility` for all services.
- **Liquidity math**:
  - Internal calculations use lamports, decimals only for logging/exports.
- **On-chain pricing**:
  - Supports multiple base tokens (SOL, USDC, USDT, USD1).
  - Automatically fetches SOL/USD when SOL is base.
- **Cleaner pool detection**:
  - PDA detection chooses owner with largest WSOL+token balance.
  - Migrated pools logged with `MIGRATED` flag.
- **Code organization**:
  - Removed duplicate `KNOWN_BASES` scattered across files.
  - Grouped liquidity, price, and pool logic into one analyzer.

### Fixed
- **Launch price calculation** — no longer duplicates SOL/USD fetches.
- **Reserves parsing** — decimals and lamports handled consistently.
- **Signature handling**:
  - `verify_signature` retries up to 3 times and safely logs empty responses.
  - Token mints cleaned up correctly after exit triggers.
- **Excel outputs**:
  - Consistent open/closed positions workflow.
  - Exit PnL properly calculated only after finalization.
- **Logging**:
  - Clearer info for liquidity missing or unknown base tokens.
  - Exit triggers + token removals logged explicitly.


## [2.3.0] – Initial Release
- Basic sniper functionality with Helius detection + Jupiter trading.
- Simulation mode and basic CSV logging.
- UI dashboard prototype.
