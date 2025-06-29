# 🚀 Solana Sniper Bot

## Overview

**Solana Sniper Bot** is a high-performance, real-time trading automation tool designed to detect, evaluate, and act on newly launched tokens on the Solana blockchain.

It connects directly to **Helius WebSocket logs** to monitor real-time token mints (via **Raydium**, **Pump.fun**, and others), and runs advanced **anti-scam checks** including liquidity validation, contract safety, holder distribution, and price manipulation.

🧠 If a token passes all checks, the bot can **automatically simulate or execute trades** via **Jupiter's AMM aggregator**, then monitor the token for take-profit or stop-loss conditions.

---

## 📚 Table of Contents

- [Prerequisites](#prerequisites)  
- [Features](#features)  
- [Requirements](#requirements)  
- [Installation](#installation)  
- [Running the Bot](#running-the-bot)  
- [Roadmap](#roadmap)  
- [Log Management](#log-management)  
- [Disclaimer](#disclaimer)  
- [License](#license)

---

## ✅ Prerequisites

You'll need the following before running the bot:

- A funded **Solana wallet**
- A **Helius API Key** (WebSocket + REST access)
- *(Optional)* **Jupiter API Key** (for price, swap, quote endpoints)
- *(Optional)* **BirdEye API Key** (for liquidity & price fallback)
- *(Optional)* A **Discord bot token** for alerts

---

## ✨ Features

- 🔎 **Real-Time Token Detection**
  - Detects brand new tokens launched via Raydium or Pump.fun
  - Pulls logs directly from the Solana blockchain via Helius

- 🛡️ **Multi-Layered Scam Detection**
  - Mint/freeze authority audit
  - Honeypot prevention via Jupiter route validation
  - High tax & suspicious price ratio checks
  - Liquidity presence via logs + Birdeye fallback
  - Largest holders & bot-wallet clustering detection

- 💸 **Trade Execution via Jupiter**
  - Full buy/sell flow using Jupiter’s swap API
  - Sends raw signed base64 transactions to Helius
  - Auto-fills token accounts if missing

- 📈 **Post-Buy Monitoring**
  - Optional safety re-check (LP lock, scam, holders)
  - Simulates 4 rounds of retry if uncertain
  - CSV logs for tracking safe vs scam token outcomes

- 🧾 **Modular Excel-Based Logging**
  - `all_tokens_found.csv` — all detected tokens
  - `safe_tokens_<date>.csv` — tokens that passed post-buy safety
  - `scam_tokens_<date>.csv` — tokens flagged as risky
  - `bought_tokens_<date>.csv` — all simulated/real trades

- 💬 **Optional Discord Integration**
  - Sends alerts for safe tokens
  - Includes price, liquidity, and token metadata

- 🧵 **Threaded Architecture**
  - WebSocket listener, transaction fetcher, delayed liquidity checker, and Discord bot all run independently for performance

---

## ⚙️ Requirements

- Python 3.8+
- `solana`, `solders`, `pandas`, `requests`, `websocket-client`, `python-dotenv`, etc.
- Dependencies listed in `requirements.txt`

---

## 🔧 Installation

### 1. Clone the repository
```bash
git clone https://github.com/AintSmurf/Solana_sniper_bot.git
cd Solana_sniper_bot
```

### 2. Create a virtual environment
On Linux/macOS:
```bash
python3 -m venv venv
source venv/bin/activate
```
On Windows:
```bash
python -m venv venv
venv\Scripts\activate
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure your credentials

Edit or export these values in `.env` or credentials utility script:

```env
API_KEY=your_helius_api_key
SOLANA_PRIVATE_KEY=your_base58_private_key
JUPITER_API_KEY=your_jupiter_api_key (optional)
BIRD_EYE_API_KEY=your_birdeye_key (optional)
DISCORD_TOKEN=your_discord_bot_token (optional)
DEX="Pumpfun" or "Raydium"
```

Linux/macOS:
```bash
sh Credentials.sh
```

Windows:
```powershell
.\Credentials.ps1
```

---

## ▶️ Running the Bot

```bash
python app.py
```

This will launch:
- WebSocket listener
- Transaction fetcher
- Position tracker (TP/SL monitor)
- Discord bot (if configured)

---

## 🛃️ Roadmap

| Feature | Status |
|--------|--------|
| ✅ Real-Time Detection via WebSocket | Completed |
| ✅ Anti-Scam Filtering | Completed |
| ✅ Buy/Sell via Jupiter | Implemented (testing phase) |
| ↺ Auto Buy Mode | Planned |
| 📲 Telegram Notifications | Planned |
| 📝 SQLite Logging (instead of CSV) | Planned |
| 💻 Web Dashboard / Windows GUI | Under testing |
| 🔐 Blacklist/Whitelist Filters | Planned |
---

## 📁 Log Management

Logs are organized for clarity and traceability:

| File              | Description                                  |
|-------------------|----------------------------------------------|
| `logs/info.log`   | All general info/debug logs                  |
| `logs/debug.log`  | Developer-focused debug messages             |
| `logs/console_logs/console.info` | Simplified console log view       |
| `logs/special_debug.log` | Critical debug logs (e.g. scam analysis)  |

---

## ⚠️ Disclaimer

This project is intended for **educational and research purposes only**. Automated trading involves financial risk. You are solely responsible for how you use this software. No guarantees are made regarding financial return or token accuracy.

---

## 📜 License

This project is licensed under the **MIT License**. See `LICENSE` file for details.

