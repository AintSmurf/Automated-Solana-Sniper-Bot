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
    #Solana blockchain mainnet- real, devnet-development/test network
    "NETWORK":"mainnet"
    
    # Whether to run the bot with a UI (tkinter dashboard)
    "UI_MODE": False,

    # Minimum liquidity required (USD) to consider a token worth trading
    "MIN_TOKEN_LIQUIDITY": 10000,

    # Maximum token age (in seconds) to be considered "fresh"
    "MAX_TOKEN_AGE_SECONDS": 30,

    # Amount (in USD) per trade (simulation or real)
    "TRADE_AMOUNT": 10,

    # Max number of successfully opened trades (real or sim) before the bot shuts down
    "MAXIMUM_TRADES": 20,

    # True = simulation mode, False = real trading
    "SIM_MODE": True,

    # Timeout conditions
    "TIMEOUT_SECONDS": 180,           # After 180s, check if profit threshold met
    "TIMEOUT_PROFIT_THRESHOLD": 1.03, # If < +3% profit → force exit
    "TIMEOUT_PNL_FLOOR": -0.03,         # Do NOT timeout if PnL is below this (e.g. -3%); let SL/TSL handle deep losses
    
    # Minimum allowed post-buy safety score (from safety_results)
    "MIN_POST_BUY_SCORE": 3,


    # Take profit and stop loss rules
    "SLPG": 3.0,                      # SLPG is a percent expressed as a float (e.g. 3.0 = 3%). The bot converts SLPG → slippageBps for Jupiter by int(SLPG * 100) (so 3.0 → 300 bps).
    "TP": 4.0,                        # +300% (4x entry)
    "SL": 0.25,                       # 25% drop from entry
    "TRAILING_STOP": 0.2,             # 20% below peak price
    "MIN_TSL_TRIGGER_MULTIPLIER": 1.5,# TSL only kicks in after 1.5x

    # Early-stop behaviour (used in check_emergency_sl)
    "EARLY_SL_SECONDS": 20,             # How long trade is treated as "fresh" after its bought for early SL logic
    "EARLY_SL_PCT": 0.07,               # -7% early-stop th

    # tokens under this USD value are eligible for dust cleanup
    "DUST_THRESHOLD_USD":1,

    # Ultra-low-latency Solana transaction submission via Helius Sender,
    # optimized for high-frequency / competitive trading.
    "USE_SENDER": {
        # Choose the region closest to your server for better landing speed.
        # Available options are listed in config/network.py.
        # maps to HELIUS_SENDER[...] in config/network.py
        "REGION": "global",

        # If True: use Helius Sender path for buy transactions.
        # Requires enough SOL for both the swap and the Jito/Helius tip.
        "BUY": False,

        # If True: use Helius Sender path for sell transactions.
        # Requires enough SOL for both the swap and the Jito/Helius tip.
        "SELL": False,
    },  


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
        "TELEGRAM": False,
        "SLACK": False,
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