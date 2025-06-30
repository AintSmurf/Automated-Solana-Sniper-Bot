from utilities.dexscanner_utility import DexscannerUtility
import pandas as pd
import os
import re 

class Analyzer:
    def __init__(self):
        self.dx = DexscannerUtility()

    def analyze_token(self, token_address,dex):
        all_pairs = self.dx.get_token_pair_address("solana", token_address)
        results = []

        if not all_pairs or not isinstance(all_pairs, list):
            print(f"❌ No pairs returned for token: {token_address}")
            return results

        for pair in all_pairs:
            try:
                liquidity = pair.get("liquidity", {}).get("usd", 0)
                if liquidity is None or liquidity < 10:
                    continue
                dex_id =  pair.get("dexId",{})
                if dex_id not in dex:
                    continue
                results.append({
                    "token": pair.get("baseToken", {}).get("address", ""),
                    "name": pair.get("baseToken", {}).get("name", ""),
                    "symbol": pair.get("baseToken", {}).get("symbol", ""),
                    "pairAddress": pair.get("pairAddress", ""),
                    "dexId": pair.get("dexId", ""),
                    "liquidity": liquidity,
                    "volume_h1": pair.get("volume", {}).get("h1", 0),
                    "volume_h24": pair.get("volume", {}).get("h24", 0),
                    "priceChange_24h": pair.get("priceChange", {}).get("h24", 0),
                    "txns_h1": pair.get("txns", {}).get("h1", {}),
                    "pairCreatedAt": pair.get("pairCreatedAt", 0),
                    "url": pair.get("url", "")
                })

            except Exception as e:
                print(f"⚠️ Error analyzing pair: {pair.get('pairAddress')} — {e}")

        return results

    def make_it_csv(self,path=None,dex=None):
        token_list = []
        if path:
            token_df = pd.read_excel(path)
            token_list = token_df["token address"].dropna().tolist()
        else:
            token_list = [
                "R63mHshFgKqg8XbvGC8cS1fnHHpcNn2uFGXFGjQ5MGF",
                "2obLASom28dxTDLJxfocejSD5emSzbESWmXuX4Fubonk",
                "4SkzBV9WKUNa6FB2qwAeiuXbcyZyfHmGo4QmLxcLbonk",
            ]
        all_data = []
        for token in token_list:
            print(f"🔍 Analyzing {token}...")
            data = self.analyze_token(token,dex)
            all_data.extend(data)

        pd.DataFrame(all_data).to_csv("missed_token_analysis.csv", index=False)
        print("✅ CSV saved: missed_token_analysis.csv")

    def run_script_on_logs(self, tokens):
        log_dir = "logs/"
        results = []

        steps = {
            "step_1_mint_instruction": "Passed Step 1",
            "step_2_blocktime": "Passed Step 2",
            "step_3_unique_signature": "Passed Step 3",
            "step_4_token_minted": "Passed Step 4",
            "liquidity_passed": "LIQUIDITY passed",
            "liquidity_failed": "Liquidity too low",
            "safety_passed": "PASSED post-buy safety check",
            "safety_failed": "FAILED post-buy safety check",
            "raw_websocket_detected": "websocket response"
        }

        for token_data in tokens:
            mint = token_data["token"]
            pair = token_data["pairAddress"]

            detection_flags = {k: False for k in steps}
            first_match = {}  # filename: line_number
            first_reason = None

            for root, _, files in os.walk(log_dir):
                for file in files:
                    if not re.match(r".*\.log(\.\d+)?$", file):
                        continue
                    file_path = os.path.join(root, file)

                    try:
                        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                            for line_num, line in enumerate(f, start=1):
                                matched = False

                                if mint in line or pair in line:
                                    if file not in first_match:
                                        first_match[file] = line_num
                                    matched = True

                                for key, marker in steps.items():
                                    if marker in line and mint in line:
                                        if not detection_flags[key]:
                                            detection_flags[key] = True
                                            if not first_reason:
                                                first_reason = key  # First reason = first failed/passed step

                                if matched and not first_reason and "websocket response" not in line:
                                    first_reason = "websocket_seen_but_not_processed"

                    except Exception as e:
                        print(f"⚠️ Error reading {file_path}: {e}")
                        continue

            # Determine final reason
            final_reason = (
                "websocket_failed" if not any(detection_flags.values()) else
                "post_buy_safety_failed" if detection_flags["safety_failed"] else
                "✅ safe" if detection_flags["safety_passed"] else
                "low_liquidity" if detection_flags["liquidity_failed"] else
                "passed_liquidity" if detection_flags["liquidity_passed"] else
                "already minted?" if detection_flags["step_4_token_minted"] else
                "incomplete chain" if detection_flags["step_1_mint_instruction"] else
                "websocket_seen_but_not_processed"
            )

            # Get the first file+line where detected
            if first_match:
                earliest_file = min(first_match, key=lambda k: first_match[k])
                earliest_line = first_match[earliest_file]
                log_ref = f"{earliest_file} (line {earliest_line})"
            else:
                log_ref = "None"

            # Build final result row
            results.append({
                "token": token_data.get("token", ""),
                "name": token_data.get("name", ""),
                "dexId": token_data.get("dexId", ""),
                "liquidity": token_data.get("liquidity", ""),
                "txns_h1": token_data.get("txns_h1", ""),
                "pairCreatedAt": token_data.get("pairCreatedAt", ""),
                "log_file": log_ref,
                "final_reason": final_reason,
            })

        df = pd.DataFrame(results)
        df.to_csv("missed_token_analysis_checked.csv", index=False)
        print("✅ Full analysis saved to missed_token_analysis_checked.csv")



if __name__ == "__main__":
    analyzer = Analyzer()
    analyzer.make_it_csv(r"analysis-29.6.xlsx",["pumpswap", "pumpfun"])
    tokens_df = pd.read_csv("missed_token_analysis.csv")
    analyzer.run_script_on_logs(tokens_df.to_dict(orient="records"))
