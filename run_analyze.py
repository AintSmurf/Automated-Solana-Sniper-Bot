import pandas as pd
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
import os

CSV_PATH = "bought_tokens_2025-07-05.csv"
EXTRACTOR_SCRIPT = "analyze.py"
MAX_WORKERS = 10  

root = os.getcwd()
token_folder = os.path.join(root,"tokens_to_track")
bought_token_folder = os.path.join(token_folder,"bought_tokens")
excel_path = os.path.join(bought_token_folder,CSV_PATH)

def run_extractor(signature, token):
    print(f"🚀 Extracting: {token}")
    subprocess.run(["python", EXTRACTOR_SCRIPT, "--signature", signature, "--token", token])

def run_all_parallel():
    df = pd.read_csv(excel_path)

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [
            executor.submit(run_extractor, row["Signature"], row["Token_bought"])
            for _, row in df.iterrows()
        ]
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as e:
                print(f"❌ Error during execution: {e}")

if __name__ == "__main__":
    run_all_parallel()
