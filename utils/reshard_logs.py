#!/usr/bin/env python3
import sys
import re
from pathlib import Path
from datetime import datetime, timezone
from collections import defaultdict
import shutil
import argparse # Import argparse

# Nginx $time_local format: [15/Nov/2025:13:51:02 +0000]
TIME_FMT = "%d/%b/%Y:%H:%M:%S %z"


def parse_time_from_line(line):
    # Find the stuff between '[' and ']'
    start = line.find('[')
    end = line.find(']', start + 1)
    if start == -1 or end == -1:
        return None
    ts_str = line[start + 1:end]
    try:
        return datetime.strptime(ts_str, TIME_FMT)
    except Exception:
        return None


def get_log_parts(path, root):
    if not path.is_file():
        return None, None

    try:
        relative_path = path.relative_to(root)
    except ValueError:
        return None, None

    parts = relative_path.parts
    filename = parts[-1]

    # an already sharded log can be identified by the date suffix
    m = re.match(r'(.+\.(?:access|junk)\.log)-(\d{4}-\d{2}-\d{2}|unparsable)$', filename)
    if m:
        base_filename = m.group(1)
    elif filename.endswith('.access.log') or filename.endswith('.junk.log'):
        base_filename = filename
    else:
        # Not a log file we recognize
        return None, None

    # Now determine archive_dir
    if len(parts) == 1:  # Top-level log
        app_name_part = base_filename.split('.')[0]
        if '.junk.' in base_filename:
            log_type = 'junk'
        else:
            log_type = 'access'
        archive_name = app_name_part.replace('-app', '') + '-archive'
        archive_dir = root / archive_name / log_type
    elif 'archive' in parts[0] and len(parts) > 1:  # Archived log
        archive_dir = path.parent
    else:
        return None, None

    return archive_dir, base_filename


def main():
    parser = argparse.ArgumentParser(description="Shard log files by timestamp.")
    parser.add_argument("--data-dir", dest="log_root_dir", default="static/data",
                        help="Path to the root directory containing log files. Defaults to 'static/data'.")
    args = parser.parse_args()

    log_root_dir = Path(args.log_root_dir).resolve()
    if not log_root_dir.is_dir():
        print(f"Log directory not found: {log_root_dir}", file=sys.stderr)
        sys.exit(1)

    all_files = [p for p in log_root_dir.rglob('*') if p.is_file()]
    
    # We'll collect all data in memory first for each app individually.
    today = datetime.now(timezone.utc).date()

    # Get app names from the directory structure
    app_names = sorted(list(set([f.name.split('-app.')[0] for f in all_files if '-app.' in f.name])))

    for app_name in app_names:
        print(f"\n--- Processing app: {app_name} ---", file=sys.stderr)
        app_files_to_process = sorted([
            p for p in all_files 
            if p.name.startswith(app_name + '-app.') and get_log_parts(p, log_root_dir)[0] is not None
        ])
        
        if not app_files_to_process:
            print(f"No log files found for {app_name}.", file=sys.stderr)
            continue

        shards = defaultdict(list)

        # --- Pass 1: Read all logs for the current app and organize them into daily lists ---
        for file_path in app_files_to_process:
            print(f"Reading {file_path.relative_to(log_root_dir)} for {app_name}", file=sys.stderr)
            try:
                with file_path.open("r", encoding="utf-8", errors="replace") as f:
                    for line in f:
                        ts = parse_time_from_line(line)
                        shard_date = ts.astimezone(timezone.utc).date() if ts else None
                        
                        archive_dir, base_filename = get_log_parts(file_path, log_root_dir)
                        if not archive_dir: continue # Should not happen with app_files_to_process filtering

                        if shard_date:
                            shard_path = archive_dir / f"{base_filename}-{shard_date.isoformat()}"
                        else:
                            shard_path = archive_dir / f"{base_filename}-unparsable"
                        
                        shards[shard_path].append(line)

            except Exception as e:
                print(f"Error reading {file_path}: {e}", file=sys.stderr)

        # --- Pass 2: Write out all shards for the current app ---
        written_shards = set()
        for shard_path, lines in shards.items():
            if not lines:
                continue

            # Deduplicate lines while preserving order
            lines = list(dict.fromkeys(lines))

            print(f"Writing shard {shard_path.relative_to(log_root_dir)} for {app_name}", file=sys.stderr)
            shard_path.parent.mkdir(parents=True, exist_ok=True)
            
            temp_path = shard_path.with_suffix(shard_path.suffix + '.tmp')
            try:
                with temp_path.open("w", encoding="utf-8") as f:
                    f.writelines(lines)
                shutil.move(temp_path, shard_path)
                written_shards.add(shard_path)
            except Exception as e:
                print(f"Error writing to {shard_path}: {e}", file=sys.stderr)
            finally:
                if temp_path.exists():
                    temp_path.unlink()

        # --- Pass 3: Clean up original files for the current app ---
        for file_path in app_files_to_process:
            is_top_level = file_path.parent == log_root_dir
            
            if is_top_level:
                todays_lines = []
                with file_path.open("r", encoding="utf-8", errors="replace") as f:
                    for line in f:
                        ts = parse_time_from_line(line)
                        if ts and ts.astimezone(timezone.utc).date() == today:
                            todays_lines.append(line)

                # Deduplicate lines while preserving order
                todays_lines = list(dict.fromkeys(todays_lines))

                if todays_lines:
                    print(f"Updating top-level log: {file_path.name}", file=sys.stderr)
                    file_path.write_text("".join(todays_lines))
                else:
                    print(f"Deleting empty top-level log: {file_path.name}", file=sys.stderr)
                    file_path.unlink()
            else:
                if file_path not in written_shards:
                    print(f"Deleting original archived log: {file_path.relative_to(log_root_dir)}", file=sys.stderr)
                    try:
                        file_path.unlink()
                    except FileNotFoundError:
                        pass
                    except Exception as e:
                        print(f"Error deleting {file_path}: {e}", file=sys.stderr)

    print("\nSharding complete.", file=sys.stderr)

if __name__ == "__main__":
    main()