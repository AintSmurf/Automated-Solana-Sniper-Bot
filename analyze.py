from utilities.dexscanner_utility import DexscannerUtility
import pandas as pd
import os
import re 

class Analyzer:
    def __init__(self):
        self.dx = DexscannerUtility()

    def analyze_token(self, token_address):
        all_pairs = self.dx.get_token_pair_address("solana", token_address)
        results = []

        if not all_pairs or not isinstance(all_pairs, list):
            print(f"❌ No pairs returned for token: {token_address}")
            return results

        for pair in all_pairs:
            try:
                liquidity = pair.get("liquidity", {}).get("usd", 0)
                if liquidity is None or liquidity < 10:
                    continue  # Skip trash

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

    def make_it_csv(self):
        token_list = [
            "R63mHshFgKqg8XbvGC8cS1fnHHpcNn2uFGXFGjQ5MGF",
            "2obLASom28dxTDLJxfocejSD5emSzbESWmXuX4Fubonk",
            "4SkzBV9WKUNa6FB2qwAeiuXbcyZyfHmGo4QmLxcLbonk",
        ]

        all_data = []
        for token in token_list:
            print(f"🔍 Analyzing {token}...")
            data = self.analyze_token(token)
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
            mint_found = False
            pair_found = False
            matched_logs = set()
            marker_sources = {}

            for root, _, files in os.walk(log_dir):
                for file in files:
                    if not re.match(r".*\.log(\.\d+)?$", file):
                        continue
                    file_path = os.path.join(root, file)
                    try:
                        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                            matched_this_file = False
                            for line in f:
                                if mint in line:
                                    mint_found = True
                                    matched_this_file = True
                                if pair in line:
                                    pair_found = True
                                    matched_this_file = True
                                for key, marker in steps.items():
                                    if marker in line and mint in line:
                                        detection_flags[key] = True
                                        marker_sources.setdefault(key, []).append(file)
                            if matched_this_file:
                                matched_logs.add(file)
                    except Exception as e:
                        print(f"⚠️ Error reading {file_path}: {e}")
                        continue

            final_reason = "unclassified"
            detailed_reason, log_file = self.trace_failure_reason(mint) if mint_found else ("no_logs", None)

            if not mint_found:
                final_reason = "websocket_failed"
            elif detection_flags["safety_failed"]:
                final_reason = "post_buy_safety_failed"
            elif detection_flags["safety_passed"]:
                final_reason = "✅ safe"
            elif detection_flags["liquidity_failed"]:
                final_reason = "low_liquidity"
            elif detection_flags["liquidity_passed"]:
                final_reason = "passed_liquidity"
            elif detection_flags["step_4_token_minted"]:
                final_reason = "already minted?"
            elif detection_flags["step_1_mint_instruction"]:
                final_reason = "incomplete chain"
            elif detection_flags["raw_websocket_detected"]:
                final_reason = "websocket_seen_but_not_processed"
            elif detailed_reason != "no_log_reason_found":
                final_reason = detailed_reason

            results.append({
                **token_data,
                **detection_flags,
                "mint_detected": mint_found,
                "pair_detected": pair_found,
                "final_reason": final_reason,
                "detailed_trace": detailed_reason,
                "log_file_match": "; ".join(sorted(matched_logs)) if matched_logs else "None",
                "log_file_trace": log_file or "None",
            })

        df = pd.DataFrame(results)
        df.to_csv("missed_token_analysis_checked.csv", index=False)
        print("✅ Full analysis saved to missed_token_analysis_checked.csv")


    
    def trace_failure_reason(self, mint):
        log_dir = "logs/"
        reasons_map = {
            "empty_websocket_message": "❌ Received an empty WebSocket message.",
            "json_decode_error": "❌ Error decoding WebSocket message:",
            "tx_custom_error": "⚠️ TX failed with custom error",
            "tx_non_custom_error": "⚠️ TX failed with non-custom error",
            "no_mint_instruction": "⛔ Skipping failed TX with no mint activity.",
            "old_transaction": "⚠️ Ignoring old transaction:",
            "duplicate_signature": "⏩ Ignoring duplicate signature from queue",
            "no_valid_token_mint": "⚠️ No valid token mint found",
            "already_minted_token": "⏩ Ignoring token",
            "low_liquidity": "⛔ Liquidity too low",
            "scam_code_detected": "failed: scam_functions_detected",
            "bad_holder_distribution": "failed: bad_holder_distribution",
            "post_buy_safety_failed": "FAILED post-buy safety check",
        }

        found_reasons = set()
        matching_files = set()

        for root, _, files in os.walk(log_dir):
            for file in files:
                if not re.match(r".*\.log(\.\d+)?$", file):
                    continue
                file_path = os.path.join(root, file)

                try:
                    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                        for line in f:
                            if mint in line:
                                for reason_key, pattern in reasons_map.items():
                                    if pattern in line:
                                        found_reasons.add(reason_key)
                                        matching_files.add(file)
                        f.seek(0)
                        for line in f:
                            for reason_key, pattern in reasons_map.items():
                                if pattern in line and mint not in line:
                                    found_reasons.add(reason_key + "_general")
                                    matching_files.add(file)
                except Exception as e:
                    print(f"⚠️ Error reading {file_path}: {e}")

        if not found_reasons:
            return "no_log_reason_found", []
        return "; ".join(sorted(found_reasons)), sorted(matching_files)




if __name__ == "__main__":
    analyzer = Analyzer()
    analyzer.make_it_csv()

    tokens_df = pd.read_csv("missed_token_analysis.csv")
    analyzer.run_script_on_logs(tokens_df.to_dict(orient="records"))
