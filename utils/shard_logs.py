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
    parser.add_argument("log_root_dir", nargs="?", default="static/data",
                        help="Path to the root directory containing log files. Defaults to 'static/data'.")
    args = parser.parse_args()

    log_root_dir = Path(args.log_root_dir).resolve()
    if not log_root_dir.is_dir():
        print(f"Log directory not found: {log_root_dir}", file=sys.stderr)
        sys.exit(1)

    all_files = [p for p in log_root_dir.rglob('*') if p.is_file()]
    
    # Identify all potential shard paths first and clear them to ensure a clean run
    all_shard_paths = set()
    for file_path in all_files:
        archive_dir, base_filename = get_log_parts(file_path, log_root_dir)
        if archive_dir:
            # This doesn't know the date, so we can't know the exact shard path.
            # Deleting all files in the archive dir is too risky.
            # A better approach is to write to temp files and then move.
            pass
    
    # For simplicity and to avoid deleting wrong files, we will build new files
    # and then replace old ones. We'll collect all data in memory first. This
    # is a rollback of the no-buffering idea, but with the *correct* logic.

    files_to_process = sorted([p for p in all_files if get_log_parts(p, log_root_dir)[0] is not None])
    
    shards = defaultdict(list)
    today = datetime.now(timezone.utc).date()

    # --- Pass 1: Read all logs and organize them into daily lists, preserving order ---
    for file_path in files_to_process:
        print(f"Reading {file_path.relative_to(log_root_dir)}", file=sys.stderr)
        try:
            with file_path.open("r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    ts = parse_time_from_line(line)
                    shard_date = ts.astimezone(timezone.utc).date() if ts else None
                    
                    archive_dir, base_filename = get_log_parts(file_path, log_root_dir)
                    if not archive_dir: continue

                    if shard_date:
                        shard_path = archive_dir / f"{base_filename}-{shard_date.isoformat()}"
                    else:
                        shard_path = archive_dir / f"{base_filename}-unparsable"
                    
                    shards[shard_path].append(line)

        except Exception as e:
            print(f"Error reading {file_path}: {e}", file=sys.stderr)

    # --- Pass 2: Write out all shards, preserving original collected order ---
    written_shards = set()
    for shard_path, lines in shards.items():
        if not lines:
            continue
        print(f"Writing shard {shard_path.relative_to(log_root_dir)}", file=sys.stderr)
        shard_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Use temp file to avoid race conditions or corruption
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

    # --- Pass 3: Clean up original files ---
    for file_path in files_to_process:
        is_top_level = file_path.parent == log_root_dir
        
        if is_top_level:
            todays_lines = []
            with file_path.open("r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    ts = parse_time_from_line(line)
                    if ts and ts.astimezone(timezone.utc).date() == today:
                        todays_lines.append(line)

            if todays_lines:
                print(f"Updating top-level log: {file_path.name}", file=sys.stderr)
                file_path.write_text("".join(todays_lines))
            else:
                print(f"Deleting empty top-level log: {file_path.name}", file=sys.stderr)
                file_path.unlink()
        else: # It's an archived file that was processed
            # Delete it only if it wasn't one of the final written shards
            if file_path not in written_shards:
                print(f"Deleting original archived log: {file_path.relative_to(log_root_dir)}", file=sys.stderr)
                try:
                    file_path.unlink()
                except FileNotFoundError:
                    pass
                except Exception as e:
                    print(f"Error deleting {file_path}: {e}", file=sys.stderr)


    print("Sharding complete.", file=sys.stderr)


if __name__ == "__main__":
    main()