# 🚀 Solana Sniper Bot

## Overview

**Solana Sniper Bot** is a high-performance, real-time trading automation tool designed to detect, evaluate, and act on newly launched tokens on the Solana blockchain.

It connects directly to **Helius WebSocket logs** to monitor real-time token mints (via **Raydium**, **Pump.fun**, and others), and runs advanced **anti-scam checks** including liquidity validation, contract safety, holder distribution, and price manipulation.

🧠 If a token passes all checks, the bot can **automatically simulate or execute trades** via **Jupiter's AMM aggregator**, then monitor the token for take-profit or stop-loss conditions.

---

## 📚 Table of Contents

- [Prerequisites](#Prerequisites)  
- [Features](#✨ Features)  
- [Requirements](#requirements)
- [Config Files Overview](#config-files-overview)  
- [Installation](#installation)  
- [Running the Bot](#running-the-bot)  
- [Roadmap](#roadmap)  
- [Log Management](#log-management)
- [Log Summarization Tool (`run_analyze.py`)](#log-summarization-tool)
- [Disclaimer](#disclaimer)  
- [License](#license)

---

## ✅ Prerequisites

You'll need the following before running the bot:

- A funded **Solana wallet**
- A **Helius API Key** (WebSocket + REST access)
- A **SOLANA_PRIVATE_KEY** — wallet key
- A **Discord bot token** — for notifications
- *(Optional- not used in the bot itself yet)* **BirdEye API Key** (for liquidity & price fallback)

---

## ✨ Features

- 🔍 **Real-Time Token Detection**
  - Captures new tokens via Helius WebSocket

- 📊 **Excel Logging System**  
  - `all_tokens_found.csv` — Every detected token with liquidity > 1500
  - `safe_tokens_YYYY-MM-DD.csv` — Tokens that passed full post-buy safety checks
  - `bought_tokens_YYYY-MM-DD.csv` — Simulated or executed buy transactions  
  - `scam_tokens_YYYY-MM-DD.csv` — Tokens flagged as scam/risky after checks

- 🛡️ **Scam Protection**
  - Mint/freeze authority audit
  - Honeypot & zero-liquidity protection
  - Tax check and centralized holder detection
  - Rug-pull risk detection (LP lock, mutability)

- 💰 **Automated Trading**
  - Buy/sell via Jupiter using signed base64 transactions
  - Handles associated token accounts automatically

- 📈 **Post-Buy Monitoring**
  - Retry safety checks (e.g., LP unlock, holder dist.)
  - Live tracking of token price vs entry price (TP/SL)

- 🧾 **Logging & Reporting**
  - CSV-based history for all trades and safety evaluations

- 💬 **Optional Discord Alerts**
  - Sends safe token alerts + price + metadata

- 🧵 **Threaded Execution**
  - WebSocket, transaction fetcher, position_tracker, and Discord bot run concurrently

- 🧠 **Log Summarization Script (`run_analyze.py`)**  
  - Extracts time-sorted logs per token for deep analysis
  - Removes duplicates, merges info/debug, and creates human-readable `.log` files


---

## ⚙️ Requirements

- Python 3.8+
- Key packages:  
  `solana`, `solders`, `pandas`, `requests`, `websocket-client`

---
## 🧩 Config Files Overview

The bot is modular and settings are managed through configuration files:

| File | Purpose |
|------|---------|
| `config/bot_settings.py` | Core parameters (TP/SL, liquidity threshold, SIM mode, rate limits) |
| `config/dex_detection_rules.py` | Per-DEX rules for token validation |
| `config/blacklist.py` | Known scam or blocked token addresses |
| `config/credentials.sh` / `.ps1` | Stores API keys and private key environment exports |

Make sure to customize these to match your risk level and DEX preferences.


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

Edit or export these values in `credentials` or credentials utility script:

```env
HELIUS_API_KEY=your_helius_api_key
SOLANA_PRIVATE_KEY=your_base58_private_key
DISCORD_TOKEN=your_discord_bot_token
BIRD_EYE_API_KEY=your_birdeye_key (optional)
DEX="Pumpfun" or "Raydium"
```
### 5. Configure bot settings `bot_settings.py`
```env
BOT_SETTINGS = {
    # Minimum liquidity required (in USD) to consider a token worth evaluating/trading
    "MIN_TOKEN_LIQUIDITY": 1500,

    # Maximum age (in seconds) of a newly minted token for it to be considered "fresh"
    "MAX_TOKEN_AGE_SECONDS": 40,

    # Amount (in USD) the bot would hypothetically use to simulate a trade per token
    "TRADE_AMOUNT": 10,
    
    # MAXIMUM_TRADES limits how many tokens the bot will attempt to trade before stopping.
    # This acts as a pain-control mechanism to avoid overtrading or unexpected loops.
    "MAXIMUM_TRADES": 20,  # ☠️ Fail-safe: Change this if you want more/less trades per session


    # flag for toggling real vs simulated trading 
    "SIM_MODE": True,

    # Take profit multiplier — e.g., 1.3 means +30% from entry price
    "TP": 4.0,

    # Stop loss multiplier — e.g., 0.95 means -5% from entry price
    "SL": 0.5,

    # Rate limiting configuration for different APIs to avoid throttling or bans
    "RATE_LIMITS": {
        "helius": {
            # Minimum time between two requests to Helius API (in seconds)
            "min_interval": 0.02,

            # Random delay added to each Helius request (to avoid burst patterns)
            "jitter_range": (0.005, 0.01),
        },
        "jupiter": {
            # Minimum time between two requests to Jupiter API (in seconds)
            "min_interval": 1.1,

            # Random delay added to each Jupiter request (to avoid burst patterns)
            "jitter_range": (0.05, 0.15),
            
            # max requests per second
            "max_requests_per_minute": 60 
        }
    },
}
```

Linux/macOS:
```bash
source Credentials.sh
```

Windows:
```powershell
.\Credentials.ps1
```

---

## ▶️ Running the Bot

> ⚠️ WARNING: If `SIM_MODE` is set to `False`, the bot will perform **real trades** on Solana using your private key.
> 🧯 **Fail-Safe Notice:** The bot includes a `MAXIMUM_TRADES` limit (default 20) to stop execution once too many trades occur. You can raise/lower this value in `bot_settings.py`.

```bash
python app.py
```

This will launch:
- WebSocket listener
- Transaction fetcher
- Position monitor (TP/SL)
- Discord bot (if configured)
---
## 🧱 Docker Setup (Optional)
- You can run the bot inside Docker using the provided **Dockerfile.bot**
  - Step 1: Make sure credential.sh configured
  ```env
    HELIUS_API_KEY=your_helius_api_key
    SOLANA_PRIVATE_KEY=your_base58_private_key
    DISCORD_TOKEN=your_discord_bot_token 
    BIRD_EYE_API_KEY=your_birdeye_key (optional)
    DEX="Pumpfun" or "Raydium"
    ```
    - Step 2: Build the Docker image
    ```bash
    docker build -f Dockerfile.bot -t solana-sniper-bot
    ```
    - Step 3: Run the bot inside Docker
    ```bash
    docker run solana-sniper-bot
  ```

## 🛃️ Roadmap

| Feature | Status |
|--------|--------|
| ✅ Real-Time Detection via WebSocket | Completed |
| ✅ Anti-Scam Filtering | Completed |
| ✅ Buy/Sell via Jupiter | Completed |
| ✅ Auto Buy Mode | Completed |
| 📲 Telegram Notifications | Planned |
| 📝 SQLite Logging (instead of CSV) | Planned |
| 💻 Web Dashboard / Windows GUI | Planned |
| 🔐 Blacklist/Whitelist Filters | ✅ Testing  |
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
---

## 🧠 Log Summarization Tool

This tool allows you to extract, clean, and analyze logs for a specific token address and transaction signature.

### 🔎 What It Does

- Searches logs in `logs/debug/`, `logs/backup/debug/`, and `logs/info.log`
- Merges entries based on signature (debug) and token (info)
- Removes duplicate lines (even if formatted differently)
- Sorts everything chronologically
- Outputs to: `logs/matched_logs/<token_address>.log`

### 🛠 Usage

```bash
python analyze.py --signature <txn_signature> --token <token_address>
```

## ⚠️ Disclaimer

This project is intended for **educational and research purposes only**. Automated trading involves financial risk. You are solely responsible for how you use this software. No guarantees are made regarding financial return or token accuracy.

---

## 📜 License

This project is licensed under the **MIT License**. See `LICENSE` file for details.

