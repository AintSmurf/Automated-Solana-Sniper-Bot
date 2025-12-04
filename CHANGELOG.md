# Changelog

All notable changes to this project will be documented in this file.  

---

## [3.4.2] – Global SIM Exits & Manual Close Consistency

### Changed
- **Global SIM exit pipeline**
  - `OpenPositionTracker._handle_exit()` now branches *only* on the global `SIM_MODE` flag:
    - When `SIM_MODE = true`:
      - Skips `TraderManager.sell()` entirely (no on-chain swaps in SIM mode).
      - Writes a synthetic sell signature (`SIMULATED_SELL_<timestamp>`).
      - Calls `TradeDAO.close_trade(...)` and removes the token from `active_trades`.
      - Sends a clear “Exit Triggered (SIM)” notification with trigger reason, current USD and PnL%.
    - When `SIM_MODE = false`:
      - Calls `TraderManager.sell()` as before.
      - Relies on `TraderManager._on_sell_status()` to finalize and close the trade in the DB.
      - Logs a warning (but does not close the trade) if the SELL transaction fails.
  - This makes SIM mode strictly DB-only and real mode strictly on-chain, with no mixed “sim trade but real sell” behavior.

- **Manual close behavior aligned with SIM mode**
  - `OpenPositionTracker.manual_close()` now mirrors the same global SIM semantics:
    - In SIM mode:
      - Does **not** call `TraderManager.sell()`.
      - Writes `SIMULATED_MANUAL_<timestamp>` as the sell signature.
      - Immediately closes the trade in the DB via `TradeDAO.close_trade(...)` and removes it from `active_trades`.
    - In real mode:
      - Performs a real sell via `TraderManager.sell()`.
      - Only closes the trade if a valid transaction signature is returned.
      - If the SELL fails (no signature), the trade is left open and the method returns `False`.

### Fixed
- **Residual inconsistencies between automatic vs manual exits in SIM mode**
  - Previously, some code paths still attempted a real `sell()` even when `SIM_MODE = true`, relying on `if not sig and SIM_MODE` as a fallback.
  - This could:
    - Log confusing “SELL failed” warnings in pure simulation runs, and
    - Make automatic and manual exits behave slightly differently.
  - Now, both automatic exits (TP/SL/TSL/timeout) and `manual_close()`:
    - Never touch the chain when `SIM_MODE = true`,
    - Always close trades purely through the database, and
    - Produce consistent SIM-specific logs and notifications.


## [3.4.1] – Buy Limit Semantics & Notification Channels

### Added
- **Configurable notification channels**
  - New settings structure for multi-channel alerts:
    ```json
    {
      "DISCORD": {
        "LIVE_CHANNEL": "live",
        "NEW_TOKENS_CHANNEL": "new-tokens"
      },
      "TELEGRAM": {},
      "SLACK": {}
    }
    ```
  - `NotificationManager` can now route messages using logical hints (e.g. `"live"`, `"new_tokens"`) instead of hard-coding Discord channel names.
  - Ready for future Telegram / Slack integration using the same pattern.

### Changed
- **TradeCounter semantics (MAXIMUM_TRADES)**
  - `TradeCounter.increment()` is now called only when a trade is **actually created and tracked**:
    - **Real trades** — increment happens inside `TraderManager._on_buy_status()` *after*:
      - Signature is confirmed/finalized,
      - Token balance is visible in the wallet,
      - Trade row is inserted into the DB,
      - Trade is added into `OpenPositionTracker.active_trades`.
    - **Simulated trades** — increment happens inside `_insert_simulated_trade()` right after inserting the SIM trade and caching it in `active_trades`.
  - The buy path **no longer increments** immediately after calling `buy(...)` from the detection layer:
    - This means failed quotes, RPC errors, or transactions that never confirm **do not consume** a trade slot.
    - `MAXIMUM_TRADES` now reflects “how many trades were **successfully opened** (real or sim)” rather than “how many buy attempts were made.”
  - Behavior note:
    - Multiple buys can still be broadcast in parallel if they pass `reached_limit()` before any trade finalizes.
    - In those edge cases, the bot may briefly have more than `MAXIMUM_TRADES` live positions, but all of them will still be tracked and eligible for exit (TP/SL/TSL/timeout).

- **Open position detection alignment**
  - `OpenPositionTracker.has_open_positions()` now cleanly reflects the full lifecycle:
    - Considers in-flight buys via `TraderManager.has_pending_trades()` (background `verify_signature` futures).
    - Considers in-memory `active_trades` with statuses: `FINALIZED`, `SELLING`, `SIMULATED`.
    - Falls back to `TradeDAO.get_live_trades(SIM_MODE)` which returns the same status set from the DB.
  - Ensures the orchestrator and shutdown logic respect:
    - Pending signature verifications,
    - Both real and simulated open trades,
    - Recovered state on restart via the DB.

### Fixed
- **False consumption of trade slots on failed buys**
  - Previously, the detection layer incremented `TradeCounter` immediately after calling `buy(...)`, even if:
    - Jupiter quote failed,
    - The transaction send failed,
    - Signature verification never finalized,
    - The token never appeared in the wallet.
  - This caused `MAXIMUM_TRADES` to be hit early while fewer real trades existed in the DB.
  - Now, only successfully finalized (or simulated) trades increment the counter, fixing under-trading caused by failed attempts.
  
---

## [3.4.0] – Trade Lifecycle Hardening & Analytics

### Added
- **Log / DB analysis tooling**
  - `bot_scripts/analyze.py` — extracts, de-duplicates, and time-sorts logs per token:
    - Scans `logs/debug/`, `logs/backup/debug/`, and `logs/info.log`.
    - Matches by `--signature` (txn) and `--token` (mint).
    - Writes merged output to `logs/matched_logs/<token>.log`.
  - `bot_scripts/run_analyze.py` — batch runner over DB:
    - Builds DB context and queries `TokenDAO.fetch_mint_signature(...)`.
    - Runs `analyze.py` in parallel for each `(signature, token)` pair.
    - CLI filters:
      - `--reason {lost,tp,sl,tsl,timeout,manual}`
      - `--today`, `--since YYYY-MM-DD`, `--all`, `--limit N`.
  - `bot_scripts/produce_summary.py`:
    - Generates `summary_results.xlsx` with:
      - **Summary** sheet: per-trade details (token, buy/sell events, prices, PnL%, exit reason, safety score, marketcap).
      - **PerSession** sheet: grouped performance per “trading day” (07:00 → next-day 07:00 in local timezone).
    - Uses the machine’s local timezone offset to compute sessions and supports win/loss counts per session.

### Changed
- **Trade status model & lifecycle**
  - Introduced explicit `SELLING` status:
    - `TraderManager.sell()` marks the DB trade as `SELLING` before broadcasting the swap transaction.
    - Prevents reconciliation from incorrectly treating in-flight exits as LOST.
  - Clarified “live” vs “historical” trades:
    - `TradeDAO.get_live_trades()` now returns only `FINALIZED`, `SELLING`, and `SIMULATED` trades.
    - `OpenPositionTracker.has_open_positions()`:
      - Checks in-memory `active_trades` for those statuses.
      - Falls back to `get_live_trades()` in the DB.
      - Ignores `RECOVERED` and `CLOSED` when deciding if the bot can shut down.

- **Wallet↔DB reconciliation v3**
  - `_reconcile_wallet_with_db()` now:
    - Snapshots `active_trades` under a lock to avoid races.
    - Filters wallet tokens by USD value using `DUST_THRESHOLD_USD` and cached prices.
    - Skips:
      - Tokens that are in `active_trades`.
      - Trades with `status='SELLING'`.
    - Only:
      - Creates `RECOVERED` trades when a non-dust token exists in the wallet but is missing in DB and not active.
      - Marks trades as `LOST` when the token is missing from the wallet, **not** active, and **not** in `SELLING`.

- **Shutdown behavior**
  - `BotOrchestrator.run_cli_loop()` now coordinates with a stricter definition of “open positions”:
    - Buying stops once `TradeCounter` hits `MAXIMUM_TRADES`.
    - The bot waits until:
      - No pending signature verifications remain (via `TraderManager.pending_futures`),
      - No active in-memory trades are `FINALIZED` / `SELLING` / `SIMULATED`,
      - No matching live trades exist in the DB,
    - Only then performs a full shutdown.
  - Fixes the case where the bot previously could shut down immediately after broadcasting the last BUY, before it was finalized and tracked.

### Fixed
- **False LOST / RECOVERED states**
  - Fixed a bug where tokens being sold or actively tracked could be:
    - Marked as `LOST` during reconciliation if the wallet/DB view was momentarily out of sync.
    - Re-created as `RECOVERED` even though they were already in `active_trades`.
  - Reconciliation now respects both `active_trades` and `SELLING` status, eliminating mid-TP/SL misclassifications.

- **Stuck “last trade” when hitting MAX_TRADES**
  - Previously, the last trade could be broadcast just before shutdown logic ran, causing:
    - `has_open_positions()` to see no open trades (not yet finalized),
    - the bot to shut down while a real open position still existed.
  - Now, pending signature verifications and live DB trades are included in the “open positions” check, ensuring the bot only shuts down when **all** trades for that run are fully resolved.

- **Dust / spam token impact on reconciliation**
  - Very small USD-value balances (below `DUST_THRESHOLD_USD`) are now:
    - Logged as dust.
    - Ignored for recovery / loss decisions.
  - Prevents tiny/airdrop tokens from polluting recovery logic or keeping the bot “busy” unnecessarily.

## [3.3.0] – Helius Sender Integration & Dust Cleaner

### Added
- **Helius Sender integration for Jupiter swaps**
  - New `get_swap_transaction_for_sender()` in the Jupiter client:
    - Requests a legacy Jupiter swap transaction (`asLegacyTransaction = True`).
    - Decompiles the message into `Instruction`s.
    - Prepends a single SOL tip transfer (using a random Helius tip wallet from `FEE_WALLETS`).
    - Rebuilds a legacy `Transaction` using Jupiter’s original `recent_blockhash`.
  - New `send_via_sender()` helper in the Helius client to:
    - Send base64-encoded transactions to the configured Sender endpoint.
    - Use `skipPreflight: true` and `maxRetries: 0` as required by Sender.
    - Optionally simulate or confirm the transaction and log any on-chain errors.

- **Dynamic Jito-based tipping**
  - New `_get_dynamic_tip_sol()` helper:
    - Calls Jito’s `/bundles/tip_floor` API.
    - Uses the 75th percentile landed tip as the dynamic fee.
    - Enforces a minimum of `0.001` SOL.
  - Integrates with the Sender swap path for smarter prioritization fees.

- **Dust Cleaner utility**
  - New `clean_dust_tokens(dust_threshold_usd: float = 1)` in the wallet client:
    - Fetches SPL token balances via Helius.
    - Uses Jupiter to compute each token’s USD value.
    - Ignores base tokens from `KNOWN_TOKENS`.
    - For low-value positions (`usd_value < dust_threshold_usd` and `ui_amount > 0`):
      - Finds the correct ATA via `get_token_accounts_by_owner`.
      - Builds a `burn` instruction for the full raw `amount`.
      - Builds a `close_account` instruction to send reclaimed rent back to the main wallet.
      - Compiles a `MessageV0` with `[burn_ix, close_ix]`, signs a `VersionedTransaction`, and sends it through Helius.
    - Logs each cleaned token and its signature, and returns the list of closed mints.

### Changed
- **Sender swap transaction construction**
  - Removed extra custom compute-budget instructions from the Sender path to avoid conflicts with Jupiter’s own CU ixs.
  - Now always reuses Jupiter’s original `recent_blockhash` when rebuilding the legacy transaction.
  - Simplified instruction ordering: `tip_ix` first, followed by the original Jupiter swap instructions.

- **Buy flow integration**
  - Real buy pipeline can now select between:
    - Standard RPC `send_transaction`, or
    - Helius Sender path (for low-latency priority routes),
    while keeping the same DB persistence and open-position tracking logic.

### Fixed
- **Timeouts on Sender-submitted swaps**
  - Resolved issues where modified Jupiter transactions would never finalize due to:
    - Blockhash mismatch,
    - ALT/compute-unit instruction mismatches, or
    - Over-modified message layouts.
  - Sender swaps now land reliably when there is sufficient SOL for both:
    - The swap route, and
    - The configured Jito tip amount.


## [3.2.0] – Database Migration & UI Overhaul

### Added
- **Full Database Integration (PostgreSQL)**  
  - Migrated from CSV-based storage to SQL-backed persistence.  
  - Introduced `SqlDBUtility`, `TradeDAO`, `SignatureDAO`, and `TokenDAO`.  
  - Automatic reconnection + rollback safety for failed inserts.  
  - All trades persist entry/exit USD, timestamps, PnL%, and trigger reasons.  
  - `RECOVERED` and `LOST` trade states fully supported for reconciliation.  

- **DAO Layer**  
  - Dedicated Data Access Objects for tokens, trades, and signatures.  
  - Clean separation of business logic from persistence layer.  
  - Safe UPSERT logic to prevent duplicate signatures or trades.  
  - Guarantees data consistency between simulation and real trading modes.  

- **UI Overhaul (`SniperBotUI`)**  
  - Responsive tkinter interface with Live & Closed Trades panels.  
  - Manual trade closing directly from the UI.  
  - Dynamic refresh of wallet, trade count, and API usage.  
  - New **Settings** and **Logging** panels with real-time control toggles.  

- **LoggingPanel Enhancements**  
  - Thread-safe UI queue updates.  
  - Hover highlighting + action column (`❌ Close Trade`).  
  - Filters for type, token, and time.  
  - Sold trades disappear instantly after exit event.  

- **Simulation Mode Rewrite**  
  - Each simulated trade uses a unique signature (`SIMULATED_BUY_<timestamp>`).  
  - Prevents key collisions in the database.  
  - Unified handling of simulated and real trade flows.

- **OpenPositionTracker v3**  
  - DB-aware tracking logic — loads open trades from SQL on startup.  
  - Applies exit rules (TP / SL / TSL / Timeout) in live cycles.  
  - Automatically removes sold or expired trades from active tracking.  
  - UTC-aware timeout and trailing-stop evaluation.

### Changed
- **Replaced CSV persistence** with full SQL-backed tables:
  - `tokens` — mint, name, image, decimals, metadata.  
  - `trades` — buy/sell info, timestamps, USD, PnL%, status.  
  - `signatures` — buy/sell signatures + confirmation tracking.
- **Improved orchestration** — `BotOrchestrator` now initializes database clients and handles graceful thread shutdown.  
- **Unified startup flow** — consistent handling between UI, CLI, and server modes.  
- **Improved exception recovery** — DB and WebSocket reconnect automatically after transient errors.

### Fixed
- **Duplicate trade entries** — handled via SQL uniqueness and signature key guards.  
- **Recovery trade persistence** — recovered mints now saved correctly on boot.  
- **Thread safety** — all UI-bound data changes routed through safe queues.  
- **Improved PnL accuracy** — simulation and real trade math now share the same calculation pipeline.

### Planned
- **Dust Cleaner Integration** (from [3.1.1])  
  - Automatic ATA cleanup for small or empty token accounts.  
  - Will utilize `CloseAccount` logic with safe blockhash injection.  

- **Web Dashboard**  
  - Browser-based control panel for monitoring trades and logs remotely.  

- **Telegram & Slack notifications**  
  - Multi-channel alert integration for trade events and errors.

---

## [3.1.0] – Safety & Integrity Update

### Added
- **Signature finalization verification**  
  - Transactions (buy/sell) are marked *FINALIZED* only after multiple consistent confirmations.  
  - Prevents false positives when Solana RPC reports “confirmed” before true finality.  
  - Retries up to 3 times with exponential backoff and logs all confirmation counts.
- **DB–Wallet reconciliation v2**  
  - Detects tokens found in wallet but missing in DB → auto-creates *recovery trades* with `status='RECOVERED'`.  
  - Detects tokens in DB but missing in wallet → marks them as *CLOSED_LOST*.  
  - Skips base tokens like **SOL**, **USDC**, **USDT**, and **USD1** to avoid false recoveries.  
  - Recovery process inserts safely with deduplication and detailed logging.
- **Blockhash safety**  
  - All custom transactions (e.g. manual or recovery TXs) now fetch a fresh blockhash via `get_latest_blockhash()` before signing.  
  - Prevents `BlockhashNotFound` errors during network delays.
- **Safer trade finalization**  
  - `OpenPositionTracker` validates token balances before marking trades as FINALIZED.  
  - Ensures a buy is only confirmed when the new token actually exists in the wallet.

### Changed
- **TradeManager finalization flow**  
  - `_signature_finalize_callback` now focuses solely on signature verification.  
  - Entry and exit updates handled by `_update_entry_price_with_balance()` and `_update_exit_with_balance()` respectively.  
- **Reconciliation filtering**  
  - Wallet scanning now uses `get_token_balances()` instead of `get_account_balances()` to exclude SOL.  
  - Only non-base tokens are eligible for recovery.  
- **Logging improvements**  
  - All critical flows (signature verification, reconciliation, recovery, finalization) now emit structured logs with clear emoji and reason codes for easier debugging.

### Fixed
- **False "missing" recoveries** — SOL and known base tokens no longer trigger recovery.  
- **Division-by-zero** — Recovered tokens have a safe `entry_usd` epsilon to prevent NaN or infinite PnL.  
- **Blockhash errors** — All custom transactions now attach a valid recent blockhash, fixing “BlockhashNotFound.”  
- **Duplicate recoveries** — Added in-memory mint cache and SQL uniqueness constraints to prevent duplicate recovered trades.  

### Planned
- **Dust account cleaner (upcoming)**  
  - Will automatically detect and close empty or near-empty ATAs, reclaiming rent similarly to SolIncinerator.  
  - Code drafted and tested locally with Helius, pending final integration and safety guardrails.  
  - Future setting: `DUST_MIN_BALANCE` (default `0.000001`).

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
  - Provides `helius_client`, `jupiter_client` for all services.
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

---

## [2.3.0] – Initial Release
- Basic sniper functionality with Helius detection + Jupiter trading.
- Simulation mode and basic CSV logging.
- UI dashboard prototype.
