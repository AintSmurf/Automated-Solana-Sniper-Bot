import os
import argparse
from datetime import datetime
import re

DEBUG_DIR = "logs/debug"
BACKUP_DEBUG_DIR = "logs/backup/debug"
INFO_LOG = "logs/info.log"
OUTPUT_DIR = "logs/matched_logs"

os.makedirs(OUTPUT_DIR, exist_ok=True)

def extract_datetime(line):
    try:
        timestamp_str = line.split(" - ")[0]
        return datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S,%f")
    except:
        return datetime.min

def get_lines_from_dir(directory, keyword):
    matches = []
    for file in sorted(os.listdir(directory), key=lambda f: os.path.getmtime(os.path.join(directory, f))):
        path = os.path.join(directory, file)
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as f:
                matches.extend([line.strip() for line in f if keyword in line])
    return matches

def get_lines_from_file(path, keyword):
    with open(path, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if keyword in line]

def deduplicate_preserve_original(lines):
    normalized_map = {}
    for line in lines:
        normalized = re.sub(r"\s+", " ", line.strip())
        if normalized not in normalized_map:
            normalized_map[normalized] = line
    return list(normalized_map.values())

def extract_logs(signature: str, token_address: str):
    all_matches = []

    if os.path.exists(DEBUG_DIR):
        all_matches.extend(get_lines_from_dir(DEBUG_DIR, signature))

    if os.path.exists(BACKUP_DEBUG_DIR):
        all_matches.extend(get_lines_from_dir(BACKUP_DEBUG_DIR, signature))

    if os.path.exists(INFO_LOG):
        all_matches.extend(get_lines_from_file(INFO_LOG, token_address))

    all_matches = deduplicate_preserve_original(all_matches)
    all_matches.sort(key=extract_datetime)

    output_path = os.path.join(OUTPUT_DIR, f"{token_address}.log")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("### TIME-SORTED LOGS ###\n")
        f.write(f"token_bought:{token_address}\n\n")
        for line in all_matches:
            f.write(line + "\n")

    print(f"✅ {len(all_matches)} total unique lines written to {output_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extract and time-sort logs for a given token.")
    parser.add_argument("--signature", required=True, help="Transaction signature to search in debug logs.")
    parser.add_argument("--token", required=True, help="Token mint address to search in info.log.")
    args = parser.parse_args()
    extract_logs(args.signature, args.token)
