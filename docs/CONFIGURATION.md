# Config Files Overview  


| File | Purpose |  
|------|---------|  
| `config/bot_settings.py` | Core parameters (TP/SL, liquidity threshold, SIM mode, rate limits) |  
| `config/dex_detection_rules.py` | Per-DEX rules for token validation |  
| `config/blacklist.py` | Known scam or blocked token addresses |  
| `config/network.py` | Solana network constants and RPC endpoint mapping |  
| `config/third_parties.py` | Third-party endpoints (Jupiter, BirdEye, dexscreener) |  
| `services/bot_context.py` | Central context manager (API keys, settings, shared state) |  
| `credentials.sh` / `.ps1` / `.sh` | Stores API keys and private key exports (Helius,  Discord token, SOL private key, BirdEye).|


---
### Credentials & Secrets

The bot requires several private credentials (Helius API key, SOL private key, Discord bot token, optional BirdEye key). These should be provided via environment variables, a local `credentials.sh`/PowerShell script, or a `.sh` file.
```bash
export HELIUS_API_KEY=''
export SOLANA_PRIVATE_KEY=''
export DISCORD_TOKEN=''
export BIRD_EYE=''
export DEX=''
export DB_NAME=""
export DB_HOST=""
export DB_PORT=
export DB_USER=""
export DB_PASSWORD=""
```


## Configuration

```python
{
    # Solana blockchain mainnet (real) / devnet (test)
    "NETWORK": "mainnet",

    # Modes
    "SIM_MODE": True,
    "UI_MODE": False,

    # Filters
    "MIN_TOKEN_LIQUIDITY": 10000,
    "MINIMUM_MARKETCAP": 50000,
    "MAX_TOKEN_AGE_SECONDS": 30,
    "MIN_POST_BUY_SCORE": 3,

    # Trade sizing / limits
    "TRADE_AMOUNT": 10,
    "MAXIMUM_TRADES": 20,

    # Timeout behavior
    "TIMEOUT_SECONDS": 180,
    "TIMEOUT_PROFIT_THRESHOLD": 1.03,
    "TIMEOUT_PNL_FLOOR": -0.03,

    # Slippage + exits
    "SLPG": 3.0,
    "TP": 4.0,
    "SL": 0.25,
    "TRAILING_STOP": 0.2,
    "MIN_TSL_TRIGGER_MULTIPLIER": 1.5,

    # Early stop behavior
    "EARLY_SL_SECONDS": 20,
    "EARLY_SL_PCT": 0.07,

    # tokens under this USD value are eligible for dust cleanup
    "DUST_THRESHOLD_USD": 1,

    # Ultra-low-latency Solana transaction submission via Helius Sender
    "USE_SENDER": {
        "REGION": "global",
        "BUY": False,
        "SELL": False
    },

    # Exit rule toggles
    "EXIT_RULES": {
        "USE_TP": False,
        "USE_TSL": False,
        "USE_SL": False,
        "USE_TIMEOUT": False
    },

    # Notification toggles
    "NOTIFY": {
        "DISCORD": False,
        "TELEGRAM": False,
        "SLACK": False
    },

    # Notification channel mapping (only relevant if NOTIFY.<platform> is True)
    "NOTIFY_CHANNELS": {
        "DISCORD": {
            "LIVE_CHANNEL": "live",
            "NEW_TOKENS_CHANNEL": "new-tokens"
        },
        "TELEGRAM": {},
        "SLACK": {}
    },

    # API rate limits
    "RATE_LIMITS": {
        "helius": {
            "min_interval": 0.02,
            "jitter_range": [0.005, 0.01],
            "max_requests_per_minute": None,
            "name": "Helius_limits"
        },
        "jupiter": {
            "min_interval": 1.1,
            "jitter_range": [0.05, 0.15],
            "max_requests_per_minute": 60,
            "name": "Jupiter_limits"
        }
    }
}

```

### Notification Channel Mapping

- In addition to enabling/disabling notifiers via `NOTIFY`, you can control which channels the bot uses (for Discord / Telegram / Slack) via a simple mapping object:
  - `NEW_TOKENS_CHANNEL` – feed for new token detections (mint, signature, flow duration, safety info).
  - `LIVE_CHANNEL` – feed for BUY / SELL events, PnL%, and exit reasons (TP / SL / TSL / timeout / manual).

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