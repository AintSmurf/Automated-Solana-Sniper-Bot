# Roadmap

- **Backup Price Source (Birdeye / on chain / - fallback, added but not fully integrated)** — Secondary price feeds to ensure reliability when Jupiter or Helius rates fail.  

- **Volume Tracking (beta)** — Tracks USD inflows/outflows per token to identify hype and unusual activity.  
  - Currently saves snapshots but accuracy still needs improvement.  

- **Blacklist / Whitelist automated detection (planned)** — Automatically flags suspicious tokens or prioritizes trusted ones.  
  - Integrated into detection and exit rule checks.    

- **Telegram Notifications (planned)** — Send trade alerts, errors, and detection events to Telegram channels.  

- **Slack Notifications (planned)** — Push alerts and trading activity into Slack workspaces.  

- **Web Dashboard (planned)** — A lightweight web UI for remote monitoring and control.  
  - Real-time feeds: detection events, open positions, closed positions, and logs.  
  - Live charts for PnL and token price history.  
  - Remote controls: start/stop bot, trigger manual sell, adjust trading settings.  

- **Track tokens by address (planned)** — Add tokens to a watchlist by mint address (manual or via detection).  
  - Watchlist supports per-token overrides (custom TP/SL, trade size, whitelist/blacklist).  
  - Watchlist shown in UI and accessible from the web dashboard or CLI.  
- **Automated Tests (pytest)** — unit and integration tests for buy/sell flows, volume tracking, and context initialization.
- **support other chains** - bsc,polygon etc ...