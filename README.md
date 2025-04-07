# 🚀 Solana Sniper Bot

## Overview

**Solana Sniper** is an automated bot that detects and analyzes newly launched tokens on the Solana blockchain in real-time. The bot connects to Helius WebSocket logs, filters tokens deployed via Raydium, and runs them through a powerful set of anti-scam checks. Verified tokens are logged to an Excel file, while a Discord bot sends alerts to your server.

🔧 The bot includes **working buy/sell functions** – these are fully implemented but not yet triggered automatically from the token filter (still under testing).

---

## 📚 Table of Contents
- [Prerequisites](#prerequisites)
- [Features](#features)
- [Requirements](#requirements)
- [Getting Started](#getting-started)
- [Roadmap](#roadmap)
- [Separate Log Storage](#separate-log-storage)
- [Disclaimer](#disclaimer)
- [License](#license)

---

## ✅ Prerequisites

To run Solana Sniper Bot, you'll need:

- A funded **Solana Wallet**
- A **Helius API Key** (used for RPC and WebSocket)
- A **Discord Bot Token** (optional, for Discord alerts)

---

## ✨ Features

- 🧠 **Helius Log Monitoring**: Detects new token mints on Raydium instantly via WebSocket.
- 🔎 **Advanced Scam Detection**:
  - Honeypot detection
  - High-tax detection
  - Dev mint/freeze authority checks
  - Liquidity lock verification
  - Token holder distribution analysis
- 📊 **Excel Logging**:
  - `all_tokens_found.csv` — all discovered tokens
  - `safe_tokens_YYYY-MM-DD.csv` — filtered, safe tokens
- 📢 **Discord Alerts**: Sends new safe tokens to a Discord channel via a separate bot.
- 💰 **Buy/Sell Functionality**: 
  - Can calculate how much SOL to spend for a token
  - Builds, signs, and sends swap transactions (via Jupiter & Raydium)
- 🔧 **Modular Logging System**: Separates debug, info, and warning logs for cleaner analysis.

---

## ⚙️ Requirements

- Python 3.8 or higher
- Helius RPC/WebSocket access (free API key)
- Jupiter & Raydium are used under the hood

---

## 🚀 Getting Started

### 1. Clone the Repository
```bash
git clone https://github.com/AintSmurf/Solana_sniper_bot.git
cd Solana_sniper_bot
```
### 2. Set Up a Virtual Environment
On Linux/macOS:
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```
On Windows:
```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```
### 3. Configure Your Credentials
 API_KEY = 'your_helius_api_key'
 SOLANA_PRIVATE_KEY = 'your_base58_encoded_solana_wallet_key'
 DISCORD_TOKEN = 'your_discord_bot_token'

### 4. Load the Credentials
On Linux/macOS:
```bash
sh Credentials.sh
```
On Windows:
```bash
.\Credentials.ps1
```
### 4. Run the Sniper Bot
```bash
python app.py
```
## 🛠️ Roadmap

✅ Buy/Sell Functionality — implemented and under testing

🔄 Auto Buy Mode — auto-trigger buy after token passes all checks

💡 Telegram Notifications — alert system for mobile users

🔐 Token Blacklist/Whitelist — to fine-tune sniper logic

📦 Database Logging (SQLite) — persist tokens long-term

🌐 Web Dashboard/Windows GUI — real-time visualization of token activity (under testing)

## 📂 Separate Log Storage
Logs are saved in the root directory:

| File                | Description                                      |
|---------------------|--------------------------------------------------|
| info.log            | All logs including debug, info, warning, error   |
| debug.log           | Debug logs only                                  |
| log.info            | Only info and warning logs                       |
| special_debug.log   | important debugs important functions             |


## ⚠️ Disclaimer
This project is intended for educational purposes only. Cryptocurrency trading and automated bot usage involve financial risk. Use this tool at your own discretion. The author is not responsible for any losses incurred.

## 📄 License
This project is licensed under the MIT License.