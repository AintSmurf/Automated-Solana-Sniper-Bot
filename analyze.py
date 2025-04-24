import pandas as pd
import requests
import time
import os

currnet_folder = os.getcwd()
results_folder = os.path.join(currnet_folder, "results")

df = pd.read_csv("results/tokens/all_tokens_found.csv")
results = []


def get_metrics(token):
    url = f"https://api.dexscreener.com/latest/dex/search?q={token}"
    headers = {"X-API-KEY": "public"}

    try:
        r = requests.get(url, headers=headers)
        if r.status_code == 200:
            data = r.json()["data"]
            return {
                "token": token,
                "price_usd": data.get("price_usd"),
                "liquidity_usd": data.get("liquidity", {}).get("usd"),
                "volume_24h_usd": data.get("volume_24h", {}).get("usd"),
                "listed": True,
            }
    except:
        pass
    return {"token": token, "listed": False}


for token in df["Token Mint"].unique():
    result = get_metrics(token)
    results.append(result)
    time.sleep(0.25)

# Save to CSV
pd.DataFrame(results).to_csv("enriched_token_data.csv", index=False)
print("Done! File saved as enriched_token_data.csv")
