# Automated Solana Sniper Bot

![Python](https://img.shields.io/badge/python-3.8+-blue.svg)  ![License](https://img.shields.io/github/license/AintSmurf/Solana_sniper_bot)  ![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)
  

## Overview  

**Automated Solana Sniper Bot (v4.3.9)** is a modular, database-backed system for real-time token detection (Helius), automated trading (Jupiter), and position management (with live tracking, exit rules, and UI dashboard).  

The system has evolved from CSV-based simulation to full **SQL persistence**, enabling advanced analytics, smoother UI integration, and fault-tolerant trade recovery.

---
### Latest (v4.3.9)
- Improved trade lifecycle ownership between `OpenPositionTracker`, `TraderManager`, and `TradeLifecycleService`.
- Added shared active-trade cache wiring for cleaner live position tracking.
- Added DB-backed run sessions to separate bot runs and improve restart recovery.
- Improved WebSocket reliability with stale-connection detection and systemd recovery support.
- Improved shutdown behavior so `MAXIMUM_TRADES` stops new detection while open-position tracking can finish safely.
- Extracted wallet reconciliation and price-sample recording into dedicated services.


## Features

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

- **Strategy & safety tools**
  - Liquidity analyzer with per-token snapshots.
  - Volume tracking around launch.
  - Rug/safety scoring (LP, holders, volume, marketcap).

- **Database-backed**
  - PostgreSQL schema for:
    - `tokens`, `trades`, `signatures`
    - `liquidity_snapshots`, `token_volumes`
    - `token_stats`, `safety_results`, `token_pools`
  - Makes recovery, analytics, and dashboards much easier.

- **Wallet hygiene**
  - `clean_dust_tokens()` burns tiny token balances and closes token accounts to reclaim rent.

- **Multiple run modes**
  - **UI mode** – Tkinter dashboard (`SniperBotUI`) with live table view and controls.
  - **CLI mode** – terminal-only, interactive.
  - **Server mode** – headless (`--server`), ideal for VPS/Docker.

---

## Installation  

```bash
git clone https://github.com/AintSmurf/Automated-Solana-Sniper-Bot/.git
cd Automated-Solana-Sniper-Bot/
python -m venv venv
source venv/bin/activate   # On Linux/macOS
venv\Scripts\activate      # On Windows
python -m pip install --upgrade pip setuptools wheel
pip install .
python .\bot_scripts\db_initializer.py  #DB creation
```
---
## Further Documentation

For full configuration, deployment, and analysis details, see:
- [Screenshots](docs/SCREENSHOTS.md)
- [Running the Bot](docs/RUNNING_THE_BOT.md)
- [Architecture & Internals](docs/ARCHITECTURE.md)
- [Config Files Overview](docs/CONFIGURATION.md)
- [Logs & Analysis](docs/LOGS_AND_ANALYSIS.md)
- [Deployment (Docker + Ansible)](docs/DEPLOYMENT_ANSIBLE.md)
- [roadmap](docs/ROADMAP.md)
- [Changelog](CHANGELOG.md)

---

## Disclaimer

This project is intended for **educational and research purposes only**. Automated trading involves financial risk. You are solely responsible for how you use this software. No guarantees are made regarding financial return or token accuracy.

---

## License

This project is licensed under the [MIT License](LICENSE).

