BOT_SETTINGS = {
    # Minimum liquidity required (in USD) to consider a token worth evaluating/trading
    "MIN_TOKEN_LIQUIDITY": 1500,

    # Maximum age (in seconds) of a newly minted token for it to be considered "fresh"
    "MAX_TOKEN_AGE_SECONDS": 180,

    # Amount (in USD) the bot would hypothetically use to simulate a trade per token
    "TRADE_AMOUNT": 10,
    
    #MAXIMUM TRADES
    "MAXIMUX_TRADES": 10,

    # Take profit multiplier — e.g., 1.3 means +30% from entry price
    "TP": 4,

    # Stop loss multiplier — e.g., 0.95 means -5% from entry price
    "SL": 0.5,

    # Rate limiting configuration for different APIs to avoid throttling or bans
    "RATE_LIMITS": {
        "helius": {
            # Minimum time between two requests to Helius API (in seconds)
            "min_interval": 0.1,

            # Random delay added to each Helius request (to avoid burst patterns)
            "jitter_range": (0.01, 0.02),
        },
        "jupiter": {
            # Minimum time between two requests to Jupiter API (in seconds)
            "min_interval": 1.1,

            # Random delay added to each Jupiter request (to avoid burst patterns)
            "jitter_range": (0.05, 0.15),
        }
    },
}
