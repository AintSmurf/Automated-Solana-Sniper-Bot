import pandas as pd
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
import os
from datetime import datetime

EXTRACTOR_SCRIPT = os.path.join(os.path.dirname(__file__), "analyze.py")
MAX_WORKERS = 10  
data = datetime.now().strftime("%Y-%m-%d")
excel_path = os.path.join(os.path.dirname(__file__), "..", "results","tokens",f"all_tokens_found_{data}.csv")

def run_extractor(signature, token):
    print(f"🚀 Extracting: {token}")
    subprocess.run(["python", EXTRACTOR_SCRIPT, "--signature", signature, "--token", token])

def run_all_parallel():
    df = pd.read_csv(excel_path)

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [
            executor.submit(run_extractor, row["Signature"], row["Token Mint"])
            for _, row in df.iterrows()
        ]
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as e:
                print(f"❌ Error during execution: {e}")

if __name__ == "__main__":
    run_all_parallel()
