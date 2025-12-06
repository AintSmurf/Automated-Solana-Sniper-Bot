import argparse
import datetime
import gzip
import os
import glob

DEBUG_MAIN_PATTERN = os.path.join("logs", "debug", "debug.log*")
DEBUG_BACKUP_PATTERN = os.path.join("logs", "backups", "debug", "*debug.log*")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Shrink old debug logs by compressing (gzip) or deleting them."
    )

    parser.add_argument(
        "--before",
        type=str,
        required=True,
        help="Only process log files last modified before this date (YYYY-MM-DD).",
    )
    parser.add_argument(
        "--mode",
        choices=["gzip", "delete"],
        default="gzip",
        help="How to shrink logs: gzip (default) or delete.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done, but don't actually change files.",
    )
    parser.add_argument(
        "--include-backups",
        action="store_true",
        help="Also process logs in logs/backups/debug (default: only main debug dir).",
    )

    return parser.parse_args()

def _iter_debug_files(include_backups: bool):
    # Main debug rotation files: debug.log.1, debug.log.2, ...
    for path in glob.glob(DEBUG_MAIN_PATTERN):
        base = os.path.basename(path)
        if base == "debug.log":
            # Don't touch active log
            continue
        yield path

    if include_backups:
        for path in glob.glob(DEBUG_BACKUP_PATTERN):
            yield path

def _should_process(path: str, cutoff_ts: float) -> bool:
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return False
    return mtime < cutoff_ts

def _gzip_file(path: str, dry_run: bool = False) -> int:
    if path.endswith(".gz"):
        return 0

    gz_path = path + ".gz"

    if dry_run:
        if os.path.exists(path):
            orig_size = os.path.getsize(path)
            est_saved = int(orig_size * 0.5)  # rough guess
            print(f"[DRY-RUN] gzip -> {path} -> {gz_path} "
                  f"(est. saved ~{est_saved/1_000_000:.2f} MB)")
        else:
            print(f"[DRY-RUN] gzip -> {path} (file missing?)")
        return 0

    orig_size = os.path.getsize(path)

    with open(path, "rb") as f_in, gzip.open(gz_path, "wb") as f_out:
        while True:
            chunk = f_in.read(1024 * 1024)
            if not chunk:
                break
            f_out.write(chunk)

    new_size = os.path.getsize(gz_path)

    # Remove original
    os.remove(path)

    saved = orig_size - new_size
    print(
        f"[gzip] {path} -> {gz_path} | "
        f"orig={orig_size/1_000_000:.2f} MB, new={new_size/1_000_000:.2f} MB, "
        f"saved={saved/1_000_000:.2f} MB"
    )
    return saved

def _delete_file(path: str, dry_run: bool = False) -> int:
    if not os.path.exists(path):
        return 0

    size = os.path.getsize(path)

    if dry_run:
        print(f"[DRY-RUN] delete -> {path} ({size/1_000_000:.2f} MB)")
        return 0

    os.remove(path)
    print(f"[delete] {path} ({size/1_000_000:.2f} MB freed)")
    return size

def main():
    args = parse_args()

    # Parse cutoff date
    try:
        cutoff_date = datetime.date.fromisoformat(args.before)
    except ValueError:
        print("❌ Invalid --before date format. Use YYYY-MM-DD, e.g. 2025-12-05")
        return

    # Timestamp at midnight local time for that date
    cutoff_dt = datetime.datetime.combine(cutoff_date, datetime.time.min)
    cutoff_ts = cutoff_dt.timestamp()

    mode = args.mode
    dry_run = args.dry_run

    print(f"🔧 Shrinking debug logs with mode={mode}, before={cutoff_date}, dry_run={dry_run}")
    print(f"   - Main pattern: {DEBUG_MAIN_PATTERN}")
    if args.include_backups:
        print(f"   - Backup pattern: {DEBUG_BACKUP_PATTERN}")
    else:
        print(f"   - Backup logs are NOT included (use --include-backups to process them)")

    total_files = 0
    total_bytes_saved = 0

    for path in _iter_debug_files(include_backups=args.include_backups):
        if not _should_process(path, cutoff_ts):
            continue

        total_files += 1

        try:
            if mode == "gzip":
                saved = _gzip_file(path, dry_run=dry_run)
            else:
                saved = _delete_file(path, dry_run=dry_run)
            total_bytes_saved += saved
        except Exception as e:
            print(f"⚠️ Failed to process {path}: {e}")

    print("")
    print(f"✅ Done. Processed {total_files} files.")
    if not dry_run:
        print(f"   Approx freed: {total_bytes_saved/1_000_000:.2f} MB")

if __name__ == "__main__":
    main()
