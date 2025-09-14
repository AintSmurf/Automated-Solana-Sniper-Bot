# Solana Sniper Bot  

![Python](https://img.shields.io/badge/python-3.9+-blue.svg)  ![License](https://img.shields.io/github/license/AintSmurf/Solana_sniper_bot)  ![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)  

## Overview  

**Solana Sniper Bot** is a high-performance, real-time trading automation tool designed to detect, evaluate, and act on newly launched tokens on the Solana blockchain.  

It connects directly to **Helius WebSocket logs** to monitor real-time token mints (via Raydium, Pump.fun, and others), and runs advanced anti-scam checks including liquidity validation, contract safety, holder distribution, and price manipulation.  

If a token passes all checks, the bot can automatically simulate or execute trades via Jupiter's AMM aggregator, then monitor the token for take-profit, stop-loss, trailing stop, and timeout conditions.  

---

## Table of Contents  

- [Screenshots](#screenshots)  
- [Prerequisites](#prerequisites)  
- [Features](#features)  
- [Requirements](#requirements)  
- [Config Files Overview](#config-files-overview)  
- [Installation](#installation)  
- [Running the Bot](#running-the-bot)  
- [Configuration](#configuration)  
- [Roadmap](#roadmap)  
- [Log Management](#log-management)  
- [Log Summarization Tool](#log-summarization-tool)  
- [Disclaimer](#disclaimer)  
- [License](#license)  

---

## Screenshots  

### UI Dashboard (Live Trading View)  
![UI Dashboard](assets/ui_dashboard.png)  

Shows bot status, wallet balance, API usage, trade settings, and real-time closed positions with PnL tracking.  

### UI Settings  
![UI Settings](assets/ui_settings.png)  ![UI Settings](assets/ui_settings_2.png)  

Configuration panel for setting TP, SL, TSL, timeout, and enabling/disabling exit rules.  


---

## Prerequisites  

You'll need the following before running the bot:  

- A funded Solana wallet  
- A Helius API Key (WebSocket + REST access)  
- A SOLANA_PRIVATE_KEY — wallet key  
- A Discord bot token — for notifications  
- (Optional) BirdEye API Key (for liquidity & price fallback)  

---


## Features  

- Real-Time Token Detection  
  - Captures new tokens via Helius WebSocket  

- Excel Logging System  
  - `results/tokens/all_tokens_found.csv` — All detected tokens  
  - `results/tokens/post_buy_checks.csv` — Tokens flagged during post-buy safety checks (LP lock, holders, volume, market cap)  
  - `tokens_to_track/bought_tokens/simulated_tokens.csv` — Active simulated token positions  
  - `tokens_to_track/bought_tokens/simulated_closed_positions.csv` — Simulated sells and PnL logs  
  - `tokens_to_track/bought_tokens/open_positions.csv` — (If applicable) active real trades  
  - `tokens_to_track/bought_tokens/closed_positions.csv` — (If applicable) completed real trades  
  - `tokens_to_track/bought_tokens/failed_sells.csv` — Failed sell attempts after retries  
  - `results/tokens/Pair_keys.csv` — Stores token-to-pool mapping (with DEX info and migration status)  
  - `results/tokens/token_volume.csv` — Launch snapshot + tracked USD volume per token  
  - `logs/matched_logs/<token>.log` — Log summary per token from `analyze.py`  

- Scam Protection  
  - Mint/freeze authority audit  
  - Honeypot & zero-liquidity protection  
  - Tax check and centralized holder detection  
  - Rug-pull risk detection (LP lock, mutability)  

- Automated Trading  
  - Buy/sell via Jupiter using signed base64 transactions  
  - Auto buy mode  
  - Handles associated token accounts automatically  

- Post-Buy Monitoring  
  - Retry safety checks (e.g., LP unlock, holder distribution)  
  - Live tracking of token price vs entry price (TP / SL / TSL / Timeout)  

- Post-Buy Safety Checks  
  - Liquidity pool lock & mutability check  
  - Centralized holder distribution audit  
  - Market cap validation  
  - Experimental volume-based filters (not fully integrated yet)  

- Logging & Reporting  
  - CSV-based trade history and analysis  
  - Retry failed sells with configurable limits  

- Notifications  
  - Discord alerts (live safe token alerts with price + metadata)  
  - Planned: Telegram & Slack integration  

- Threaded Execution  
  - WebSocket, transaction fetcher, position tracker, and notifier run concurrently  

- Log Summarization Tool (`run_analyze.py`)  
  - Extracts time-sorted logs per token for deep analysis  
  - Removes duplicates, merges info/debug, and creates human-readable `.log` files  

### Experimental Features  
- Volume Tracking (work in progress)  
- Backup Chain Price Source and Birdeye (added, not fully integrated)  


---

## Requirements  

- Python 3.8+  
- Key packages:  
  `solana`, `solders`, `pandas`, `requests`, `websocket-client`  

---

## Config Files Overview  

| File | Purpose |  
|------|---------|  
| `config/bot_settings.py` | Core parameters (TP/SL, liquidity threshold, SIM mode, rate limits) |  
| `config/dex_detection_rules.py` | Per-DEX rules for token validation |  
| `config/blacklist.py` | Known scam or blocked token addresses |  
| `credentials.sh` / `.ps1` | Stores API keys and private key exports |  

---

## Installation  

```bash
git clone https://github.com/AintSmurf/Solana_sniper_bot.git
cd Solana_sniper_bot
python -m venv venv
source venv/bin/activate   # On Linux/macOS
venv\Scripts\activate      # On Windows
pip install -r requirements.txt
```

## Running the Bot

This bot can be launched in **three different modes**: UI mode, CLI mode, and Server mode. Each serves a unique purpose depending on your environment (local, interactive, or server-based deployment).

---

### UI Mode (Graphical Interface)

```bash
python app.py
```

- When you launch without any flags, the bot will prompt:
  ```
  Would you like to launch the bot with a graphical interface? (yes/no)
  ```
- If you answer `yes`, a graphical interface will open for configuration and live monitoring.
- **Recommended** for beginners or for manual supervision of the bot.

---

### CLI Mode (Interactive Terminal)

```bash
python app.py
```

- If you answer `no` to the UI prompt, the bot will launch in **terminal-only mode**.
- It displays logs, buys, and sells in real time.
- Also sends alerts to Discord (if configured).
- **Best for** users running the bot manually via terminal without needing a GUI.

---

### Server Mode (Headless / No Prompts)

```bash
python app.py --s or python app.py --server 
```

- **No prompts**, no UI.
- Uses your existing `bot_settings.json` to start immediately.
- Ideal for **cloud servers, VPS, or Docker containers**.
- Auto-shutdown happens after `MAXIMUM_TRADES` is reached unless customized.

---

## Configuration `bot_settings.py`

```python
{
    # Whether to run the bot with a UI (tkinter dashboard)
    "UI_MODE": True,

    # Minimum liquidity required (USD) to consider a token worth trading
    "MIN_TOKEN_LIQUIDITY": 10000,

    # Maximum token age (in seconds) to be considered "fresh"
    "MAX_TOKEN_AGE_SECONDS": 30,

    # Amount (in USD) per trade (simulation or real)
    "TRADE_AMOUNT": 10,

    # Max number of trades before the bot shuts down
    "MAXIMUM_TRADES": 20,

    # True = simulation mode, False = real trading
    "SIM_MODE": True,

    # Timeout conditions
    "TIMEOUT_SECONDS": 180,           # After 180s, check if profit threshold met
    "TIMEOUT_PROFIT_THRESHOLD": 1.03, # If < +3% profit → force exit

    # Take profit and stop loss rules
    "TP": 4.0,                        # +300% (4x entry)
    "SL": 0.25,                       # 25% drop from entry
    "TRAILING_STOP": 0.2,             # 20% below peak price
    "MIN_TSL_TRIGGER_MULTIPLIER": 1.5,# TSL only kicks in after 1.5x

    # Exit rule toggles
    "EXIT_RULES": {
        "USE_TP": False,
        "USE_TSL": False,
        "USE_SL": False,
        "USE_TIMEOUT": False
    },

    # Notification channels
    "NOTIFY": {
        "DISCORD": False,
        "DISCORD_WEBHOOK": "",
        "TELEGRAM": False,
        "TELEGRAM_CHAT_ID": "",
        "SLACK": False,
        "SLACK_WEBHOOK": ""
    },

    # API rate limits
    "RATE_LIMITS": {
        "helius": {
            "min_interval": 0.02,             # seconds between requests
            "jitter_range": [0.005, 0.01],    # randomness to avoid bursts
            "max_requests_per_minute": None,  # unlimited
            "name": "Helius_limits"
        },
        "jupiter": {
            "min_interval": 1.1,              # seconds between requests
            "jitter_range": [0.05, 0.15],     # randomness to avoid bursts
            "max_requests_per_minute": 60,    # requests per minute
            "name": "Jupiter_limits"
        }
    }
}

```

## Important Notes

- Make sure `bot_settings.json` is properly configured before using `--server` mode.
- Your private key and API keys are loaded from environment variables or `.env`/JSON securely.
- All trades in **simulation** unless you explicitly disable `SIM_MODE` in the settings.

##  Docker Setup 
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

## Roadmap

| Feature                           | Status                     |
| --------------------------------- | -------------------------- |
| Real-Time Detection via WebSocket | Completed                  |
| Post-Buy Safety Checks            | Completed                  |
| Buy/Sell via Jupiter              | Completed                  |
| Auto Buy Mode                     | Completed                  |
| Backup Price Source               | Added (not fully used yet) |
| Volume Tracking                   | (beta — tracks buy/sell USD flows per token, saves launch snapshot not accurate yet)                       |
| Telegram Notifications            | Planned                    |
| Slack Notifications               | Planned                    |
| SQLite Logging (instead of CSV)   | Planned                    |
| Windows GUI                       | Completed                  |
| Web Dashboard                     | Planned                    |
| Blacklist/Whitelist Filters       | Testing                    |

## Log Management

Logs are organized for clarity and traceability:
| File                             | Description                              |
| -------------------------------- | ---------------------------------------- |
| `logs/info.log`                  | General info/debug logs                  |
| `logs/debug.log`                 | Developer-focused debug logs             |
| `logs/console_logs/console.info` | Simplified console view                  |
| `logs/special_debug.log`         | Critical debug logs (e.g. scam analysis) |

---

## Log Summarization Tool

This tool allows you to extract, clean, and analyze logs for one or multiple token addresses and transaction signatures.

###  Functionality

- Searches across:
  - `logs/debug/`
  - `logs/backup/debug/`
  - `logs/info.log`
- Matches logs by:
  - `--signature` (transaction signature)
  - `--token` (mint address)
- Removes duplicate or overlapping lines
- Sorts all matched logs chronologically
- Outputs a clean, consolidated log to: logs/matched_logs/<token_address>.log
### Manual Usage (One Token)
To analyze a **single** token and transaction:

```bash
python analyze.py --signature <txn_signature> --token <token_address>
```
To analyze all tokens in parallel from your results:

```bash
python run_analyze.py 
```
- explanation
  - Reads results/tokens/all_tokens_found.csv
  - Extracts logs for each Signature and Token Mint pair
  - Runs `analyze.py` in parallel subprocesses 
    - (uses `max_workers=10` by default; 
    - actual concurrency depends on your CPU)


## Disclaimer

This project is intended for **educational and research purposes only**. Automated trading involves financial risk. You are solely responsible for how you use this software. No guarantees are made regarding financial return or token accuracy.

---

## License

This project is licensed under the [MIT License](LICENSE) See `LICENSE` file for details.

