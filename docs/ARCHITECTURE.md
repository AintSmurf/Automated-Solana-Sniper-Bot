# Architecture & Internals

This document dives deeper into how the bot is structured under the hood:
core runtime, database schema, strategy helpers, wallet hygiene, and notifications.

---
## Architecture Highlights
- **Detection layer** — Helius WebSocket stream + transaction analysis  
- **Execution layer** — Jupiter-powered trading via `TraderManager`  
- **Persistence layer** — PostgreSQL via `SqlDBUtility`, `TradeDAO`, `SignatureDAO`, `TokenDAO`  
- **Tracking layer** — DB-aware `OpenPositionTracker` with exit rules (TP / SL / TSL / Timeout)  
- **UI layer** — Tkinter-based dashboard (`SniperBotUI`) with live table view and manual controls  
- **Orchestration** — `BotOrchestrator` wires all services, manages async tasks and shutdown  

---
## Core System

- **Real-time token detection**
  - Helius WebSocket stream + transaction parsing.
  - Token age & liquidity filters to catch only fresh, tradeable tokens.

- **Automated trading (SIM or REAL)**
  - Buys/sells via Jupiter.
  - `SIM_MODE` for safe, realistic testing (real quotes, no on-chain swaps).
  - Real mode with optional **Helius Sender** for low-latency inclusion.

- **Exit rules**
  - Take Profit (TP)
  - Stop Loss (SL)
  - Trailing Stop Loss (TSL)
  - Timeout-based exits
  - All controlled via `config/bot_settings.json`.

- **Full multi-threaded orchestration**
  - Separate flows for detection, post-buy safety checks, and position tracking.
  - Clean shutdown once all queues are drained.

- **Robust trade lifecycle**
  - Explicit `FINALIZED` / `SELLING` / `RECOVERED` / `CLOSED` states.
  - DB–wallet reconciliation that respects in-flight exits and dust thresholds.
  - Safe auto-shutdown once all trades and pending signatures are resolved.

---

## Database Persistence

The bot uses PostgreSQL as the source of truth for tokens, trades, and analytics.

| Table                  | Purpose                                                                 |
|------------------------|-------------------------------------------------------------------------|
| `tokens`               | Mint info and metadata (token_address, first detection signature, time) |
| `trades`               | Each position: BUY/SELL, entry/exit USD, PnL%, trigger_reason, status, simulation flag, timestamps |
| `signatures`           | Buy/sell signature mapping per token + buy/sell times                  |
| `token_stats`          | Market data snapshot: market cap, holder count per token               |
| `safety_results`       | Rug/safety checks: LP, holders, volume, marketcap flags + score        |
| `token_volumes`        | Aggregated volume stats: buy/sell USD, counts, net flow, launch volume |
| `liquidity_snapshots`  | Time-series liquidity (SOL/USDC/USDT/USD1 + total) per token           |
| `token_pools`          | Pool mapping: pool address, DEX source, created_at                     |

This schema lets you:
- Rebuild PnL and trade history even after crashes.
- Run your own analytics or dashboards on top of the DB.
- Post-process “missed” or “rugged” tokens using separate tools.

---

## Strategy Tools

A few helper components support the core trading logic:

- **Liquidity analyzer**
  - Combines pool reserves into SOL / USDC / USDT / USD1.
  - Stores snapshots into `liquidity_snapshots` and `token_volumes`.

- **Volume tracker**
  - Captures volume around launch (buy/sell USD & counts).
  - Helps identify hype / abnormal activity versus dead launches.

- **Rug / safety checks**
  - Validates LP state, holder distribution, basic volume and marketcap.
  - Persists results into `safety_results` for later inspection.

---

## Wallet Hygiene

The bot includes an optional utility to keep your wallet clean:

- **Dust Cleaner (manual)**
  - `clean_dust_tokens(dust_threshold_usd=1.0)` scans your SPL balances.
  - Uses Jupiter to estimate per-token USD value.
  - For tiny positions below the threshold:
    - Builds a `burn` ix for the full raw amount.
    - Builds a `close_account` ix to reclaim rent.
    - Signs and sends a compact `MessageV0` transaction via Helius.
  - Logs each cleaned mint and its transaction signature.

This is useful after many trades where dust tokens and rent-holding accounts pile up.

---

## 🔔 Notifications

The bot can push key events to external channels:

- **Discord**
  - Live detection feed (new tokens).
  - Trade lifecycle: buys, sells, exit reasons (TP / SL / TSL / timeout / manual).

Channel mapping is configurable via a simple JSON structure (see `docs/CONFIGURATION.md` if you split it out), so you can rename channels without touching Python code.