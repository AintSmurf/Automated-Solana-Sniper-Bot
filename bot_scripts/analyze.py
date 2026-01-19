import os
import re
import gzip
import argparse
from datetime import datetime
from collections import defaultdict

DEBUG_DIR = "logs/debug"
BACKUP_DEBUG_DIR = "logs/backups/debug"
INFO_LOG = "logs/info.log"
OUTPUT_DIR = "logs/matched_logs"

os.makedirs(OUTPUT_DIR, exist_ok=True)


def extract_datetime(line: str) -> datetime:
    try:
        ts = line.split(" - ")[0]
        return datetime.strptime(ts, "%Y-%m-%d %H:%M:%S,%f")
    except Exception:
        return datetime.min

def _open_maybe_gzip(path: str):
    if path.endswith(".gz"):
        return gzip.open(path, "rt", encoding="utf-8", errors="ignore")
    return open(path, "r", encoding="utf-8", errors="ignore")

def iter_files_by_mtime(directory: str):
    if not os.path.isdir(directory):
        return
    for file in sorted(
        os.listdir(directory),
        key=lambda f: os.path.getmtime(os.path.join(directory, f)),
    ):
        path = os.path.join(directory, file)
        if os.path.isfile(path):
            yield path

def dedup_preserve(lines):
    seen = set()
    out = []
    for line in lines:
        norm = re.sub(r"\s+", " ", line.strip())
        if norm not in seen:
            seen.add(norm)
            out.append(line)
    return out

def _compile_or_regex(values):
    """
    Build a safe OR-regex: (val1|val2|...)
    For ~100 signatures/tokens this is fast and accurate.
    """
    escaped = [re.escape(v) for v in values if v]
    if not escaped:
        return None
    return re.compile(r"(" + "|".join(escaped) + r")")

def scan_debug(signature_regex, sig_to_token):
    per_token = defaultdict(list)
    if signature_regex is None:
        return per_token

    def handle_line(line: str):
        for m in signature_regex.findall(line):
            token = sig_to_token.get(m)
            if token:
                per_token[token].append(line.rstrip("\n"))

    for directory in (DEBUG_DIR, BACKUP_DEBUG_DIR):
        for path in iter_files_by_mtime(directory):
            try:
                with _open_maybe_gzip(path) as f:
                    for line in f:
                        if signature_regex.search(line):
                            handle_line(line)
            except Exception as e:
                print(f"⚠️ Failed to read {path}: {e}")

    return per_token

def scan_info(token_regex, token_set):
    per_token = defaultdict(list)
    if token_regex is None or not os.path.exists(INFO_LOG):
        return per_token

    try:
        with _open_maybe_gzip(INFO_LOG) as f:
            for line in f:
                hits = token_regex.findall(line)
                if not hits:
                    continue
                for tok in hits:
                    if tok in token_set:
                        per_token[tok].append(line.rstrip("\n"))
    except Exception as e:
        print(f"⚠️ Failed to read {INFO_LOG}: {e}")

    return per_token

def write_outputs(per_token_lines: dict, token_to_sigs: dict):
    for token, lines in per_token_lines.items():
        if not lines:
            continue
        lines = [ln for ln in lines if "with params=" not in ln]

        lines = dedup_preserve(lines)
        lines.sort(key=extract_datetime)

        out_path = os.path.join(OUTPUT_DIR, f"{token}.log")
        sigs = token_to_sigs.get(token, {})

        with open(out_path, "w", encoding="utf-8") as f:
            f.write("### TIME-SORTED LOGS ###\n")
            f.write(f"token:{token}\n")
            f.write(f"mint_signature:{sigs.get('mint_signature') or 'N/A'}\n")
            f.write(f"buy_signature:{sigs.get('buy_signature') or 'N/A'}\n")
            f.write(f"sell_signature:{sigs.get('sell_signature') or 'N/A'}\n\n")

            for line in lines:
                f.write(line + "\n")

        print(f"✅ {len(lines)} lines -> {out_path}")

def main():
    parser = argparse.ArgumentParser(
        description="Fast batch log extractor (single pass, gz-friendly)."
    )
    parser.add_argument(
        "--pairs",
        required=True,
        help="CSV with columns: token_address,mint_signature,buy_signature,sell_signature",
    )
    parser.add_argument("--limit", type=int, default=None, help="Optional limit rows from CSV")
    args = parser.parse_args()

    import csv

    rows = []
    token_to_sigs = {}

    with open(args.pairs, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            tok = (r.get("token_address") or "").strip()
            if not tok:
                continue

            mint_sig = (r.get("mint_signature") or "").strip()
            buy_sig = (r.get("buy_signature") or "").strip()
            sell_sig = (r.get("sell_signature") or "").strip()

            # normalize "none"
            mint_sig = mint_sig if mint_sig and mint_sig.lower() != "none" else ""
            buy_sig = buy_sig if buy_sig and buy_sig.lower() != "none" else ""
            sell_sig = sell_sig if sell_sig and sell_sig.lower() != "none" else ""

            sigs = [s for s in (mint_sig, buy_sig, sell_sig) if s]
            if not sigs:
                continue

            token_to_sigs[tok] = {
                "mint_signature": mint_sig,
                "buy_signature": buy_sig,
                "sell_signature": sell_sig,
            }
            rows.append((tok, sigs))

    if args.limit:
        rows = rows[: args.limit]

    if not rows:
        print(
            "⚠️ No valid rows found. Check CSV columns: token_address,mint_signature,buy_signature,sell_signature"
        )
        return

    # Build signature -> token map
    sig_to_token = {}
    for tok, sigs in rows:
        for s in sigs:
            sig_to_token[s] = tok

    signature_list = list(sig_to_token.keys())
    token_set = set(tok for tok, _ in rows)

    sig_re = _compile_or_regex(signature_list)
    tok_re = _compile_or_regex(list(token_set))

    print(f"🧠 Loaded {len(signature_list)} signatures, {len(token_set)} tokens")

    debug_hits = scan_debug(sig_re, sig_to_token)
    info_hits = scan_info(tok_re, token_set)

    merged = defaultdict(list)
    for token, lines in debug_hits.items():
        merged[token].extend(lines)
    for token, lines in info_hits.items():
        merged[token].extend(lines)

    write_outputs(merged, token_to_sigs)
    print("\n✅ Done.")


if __name__ == "__main__":
    main()
