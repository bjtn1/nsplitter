#!/usr/bin/env python3
"""
Author: Brandon Jose Tenorio Noguera
Email : nsplitter@bjtn.me

A utility that splits large files into ≤ 4 GB chunks and can merge those
chunks back together.  Useful for moving data onto FAT‑32 drives or any
media with size limits.
"""

from __future__ import annotations

import argparse
import math
import os
import shutil
import subprocess
import sys
import time
import re

# ----------------------------------------------------------------------
# Constants
# ----------------------------------------------------------------------
THIRTY_TWO_KB = 0x8000               # 32 768 bytes
FAT32_MAX_FILE_SIZE = 0xFFFFFFFF     # Largest file FAT32 can store (4 GiB - 1)
MAX_SPLIT_SIZE = 0xFFFF0000          # Chunk size: 4 GiB - 64 KiB, as splitNSP uses
FOUR_MB       = 4 * 1024 * 1024      # Buffer size for merging


# ----------------------------------------------------------------------
# Helper functions
# ----------------------------------------------------------------------
def print_banner(msg: str) -> None:
    """Print a nice banner around *msg*."""
    banner = f"== {msg} =="
    border = "=" * len(banner)
    print(f"\n{border}\n{banner}\n{border}")


def format_elapsed_time(start_time: float) -> str:
    """Return elapsed time since *start_time* as HH:MM:SS."""
    elapsed = time.time() - start_time
    hrs, rem = divmod(int(elapsed), 3600)
    mins, secs = divmod(rem, 60)
    return f"{hrs:02}:{mins:02}:{secs:02}"


def set_archive_bit(path: str) -> bool:
    """
    Set the FAT archive attribute on *path*.  The Switch only treats a folder
    of numbered parts as a single file when this attribute is set.
    Returns ``True`` on success.
    """
    if os.name == "nt":
        import ctypes
        FILE_ATTRIBUTE_ARCHIVE = 0x20
        INVALID_FILE_ATTRIBUTES = 0xFFFFFFFF
        kernel32 = ctypes.windll.kernel32
        kernel32.GetFileAttributesW.restype = ctypes.c_uint32
        attrs = kernel32.GetFileAttributesW(path)
        if attrs == INVALID_FILE_ATTRIBUTES:
            return False
        return bool(kernel32.SetFileAttributesW(path, attrs | FILE_ATTRIBUTE_ARCHIVE))

    # Linux: fatattr (from the fatattr package) works on mounted FAT drives
    if shutil.which("fatattr"):
        result = subprocess.run(["fatattr", "+a", path], capture_output=True)
        return result.returncode == 0

    return False


def is_split_path(path: str) -> bool:
    """
    Return ``True`` if *path* (file **or** directory name) matches the pattern
    ``<base>.split.<ext>``.  Trailing path separators are ignored.
    """
    name = os.path.basename(os.path.normpath(path))
    # Anything + ".split." + non‑empty extension (no dots inside the extension)
    return bool(re.fullmatch(r".+\.split\.[^.]+", name))


def merged_name_for(split_name: str) -> str:
    """Return the original filename for a ``<base>.split.<ext>`` folder name."""
    return re.sub(r"\.split(\.[^.]+)$", r"\1", split_name)


def collect_files(directory: str,
                  extension: str,
                  recursive: bool,
                  split_mode: bool) -> list[str]:
    """
    Walk *directory* and return a list of paths:

    * ``split_mode=True`` – regular files ending with ``.<extension>``
      that are **not** already split folders.
    * ``split_mode=False`` – directories whose names match the split‑folder
      pattern.
    """
    collected: list[str] = []

    for root, dirs, files in os.walk(directory):
        if split_mode:
            for f in files:
                if f.lower().endswith(f".{extension.lower()}"):
                    fp = os.path.join(root, f)
                    if not is_split_path(fp):
                        collected.append(fp)
        else:
            for d in dirs:
                dp = os.path.join(root, d)
                if is_split_path(dp) and d.lower().endswith(f".{extension.lower()}"):
                    collected.append(dp)

        if not recursive:
            break

    return collected


def split_skip_reason(path: str) -> str:
    """Return why *path* should not be split, or an empty string if it should."""
    if not os.path.isfile(path):
        return "not a file"
    if os.path.getsize(path) <= FAT32_MAX_FILE_SIZE:
        return "already fits on FAT32"
    parent = os.path.dirname(os.path.abspath(path))
    if os.path.getsize(path) > shutil.disk_usage(parent).free:
        return "insufficient free space"
    return ""


def merge_skip_reason(path: str) -> str:
    """Return why *path* should not be merged, or an empty string if it should."""
    if not is_split_path(path):
        return "not a .split.<ext> folder"
    return ""


# ----------------------------------------------------------------------
# Core operations
# ----------------------------------------------------------------------
def merge_file(folder_path: str,
               dry_run: bool = False,
               buf_size: int = FOUR_MB) -> str:
    """
    Re‑assemble a ``<name>.split.<ext>`` folder back into a single file.
    Returns the absolute path of the merged file (or an empty string on error).
    """
    folder_path = os.path.abspath(os.path.normpath(folder_path))

    if not is_split_path(folder_path) or not os.path.isdir(folder_path):
        print(f"❌ {os.path.basename(folder_path)} is not a split folder")
        return ""

    merged_name = merged_name_for(os.path.basename(folder_path))
    merged_path = os.path.join(os.path.dirname(folder_path), merged_name)

    # Gather the numeric part files in proper order, ignoring OS junk such as
    # ._00, .DS_Store, desktop.ini or Thumbs.db
    parts: dict[int, str] = {}
    for fn in os.listdir(folder_path):
        fp = os.path.join(folder_path, fn)
        if not (re.fullmatch(r"\d+", fn) and os.path.isfile(fp)):
            continue
        if int(fn) in parts:
            print(f"❌ {folder_path} has two parts numbered {int(fn):02}")
            return ""
        parts[int(fn)] = fp

    if not parts:
        print(f"❌ {folder_path} contains no numbered parts")
        return ""
    missing = sorted(set(range(max(parts) + 1)) - set(parts))
    if missing:
        print(f"❌ {folder_path} is missing part(s) "
              f"{', '.join(f'{n:02}' for n in missing)}")
        return ""

    part_files = [parts[n] for n in sorted(parts)]
    total_size = sum(os.path.getsize(p) for p in part_files)

    if os.path.exists(merged_path):
        print(f"❌ {merged_path} already exists; refusing to overwrite it")
        return ""

    if total_size > shutil.disk_usage(os.path.dirname(folder_path)).free:
        print(f"❌ Not enough free space to merge {folder_path}")
        return ""

    print_banner(f"MERGING {os.path.basename(folder_path)}")
    start = time.time()

    if dry_run:
        for part in part_files:
            print(f"ℹ️ Would merge part {os.path.basename(part)}")
        print(f"\n✅ Dry run: would merge into {merged_path}")
        return merged_path

    out_f = open(merged_path, "xb")
    try:
        with out_f:
            for part in part_files:
                print(f"ℹ️ Merging part {os.path.basename(part)}...")
                with open(part, "rb") as in_f:
                    shutil.copyfileobj(in_f, out_f, length=buf_size)
    except BaseException:
        # Don't leave a partial file behind; it would block the next attempt
        os.remove(merged_path)
        raise

    merged_size = os.path.getsize(merged_path)
    if merged_size != total_size:
        print(f"❌ {merged_path} is {merged_size} bytes but the parts total "
              f"{total_size}; keeping {folder_path}")
        return ""

    print(f"⏳ Merge took {format_elapsed_time(start)}")
    print(f"\n✅ {merged_path} successfully merged")

    shutil.rmtree(folder_path)

    return merged_path


def split_file(filepath: str,
               buf_size: int = THIRTY_TWO_KB,
               dry_run: bool = False,
               clean: bool = False) -> str:
    """
    Split *filepath* into chunks of at most ``MAX_SPLIT_SIZE`` bytes placed in
    a sibling folder ``<basename>.split.<ext>``.  Returns the absolute path of
    that folder (or an empty string on error).
    """
    filesize = os.path.getsize(filepath)
    filename = os.path.basename(filepath)

    # Number of chunks needed (ceil for partial final chunk)
    num_splits = math.ceil(filesize / MAX_SPLIT_SIZE)

    parent_dir = os.path.dirname(filepath)
    ext = os.path.splitext(filepath)[1].lstrip(".")
    base = os.path.splitext(filename)[0]
    split_dir = os.path.abspath(
        os.path.join(parent_dir, f"{base}.split.{ext}")
    )

    # Leftover parts from an earlier split would be merged in later
    if os.path.isdir(split_dir) and os.listdir(split_dir):
        print(f"❌ {split_dir} already exists and is not empty; "
              "remove it or merge it first")
        return ""

    print_banner(f"SPLITTING {filename}")

    if dry_run:
        print(f"ℹ️ Would split into {num_splits} part(s)")
        print(f"✅ Dry run: would create {split_dir}")
        return split_dir

    os.makedirs(split_dir, exist_ok=True)

    with open(filepath, "rb") as src:
        for idx in range(num_splits):
            part_path = os.path.join(split_dir, f"{idx:02}")

            start = time.time()
            last_sec = -1

            with open(part_path, "wb") as dst:
                written = 0
                while written < MAX_SPLIT_SIZE:
                    now_sec = int(time.time() - start)
                    if now_sec != last_sec:
                        print(
                            f"ℹ️ Splitting part {idx:02}... "
                            f"Elapsed: {format_elapsed_time(start)}",
                            end="\r"
                        )
                        last_sec = now_sec

                    # Never read past the chunk limit, whatever buf_size is
                    chunk = src.read(min(buf_size, MAX_SPLIT_SIZE - written))
                    if not chunk:
                        break
                    dst.write(chunk)
                    written += len(chunk)
            print()   # newline after each part’s progress line

    split_size = sum(
        os.path.getsize(os.path.join(split_dir, f"{i:02}"))
        for i in range(num_splits)
    )
    if split_size != filesize:
        print(f"❌ Parts total {split_size} bytes but {filename} is "
              f"{filesize}; keeping the original")
        return ""

    if not set_archive_bit(split_dir):
        print(f"⚠️ Could not set the archive bit on {split_dir}. "
              "Set it manually or the Switch will not see the parts as one file.")

    if clean:
        os.remove(filepath)

    print(f"✅ {split_dir} successfully split")
    return split_dir


# ----------------------------------------------------------------------
# CLI entry point
# ----------------------------------------------------------------------
def main() -> None:
    # Consoles and pipes that can't encode the emoji would otherwise crash
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")

    parser = argparse.ArgumentParser(description="Split or merge large files.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("-s", "--split", action="store_true", help="Split files")
    mode.add_argument("-m", "--merge", action="store_true", help="Merge split folders")

    parser.add_argument("-d", "--directory", help="Directory to process")
    parser.add_argument("-e", "--extension", help="File extension (e.g., mp4, nsp)")
    parser.add_argument("-r", "--recursive", action="store_true", help="Recurse into sub-folders")
    parser.add_argument("--dry-run", action="store_true", help="Simulate actions")
    parser.add_argument("--clean", action="store_true", help="Delete originals after splitting")
    parser.add_argument("files", nargs="*", help="Specific files/folders to process")
    args = parser.parse_args()

    # Resolve the list of targets (files or split folders)
    targets: list[str] = args.files[:]

    if args.directory:
        if not args.extension:
            sys.exit("❌ -e/--extension is required when using -d/--directory.")
        ext = args.extension.lstrip(".")
        to_split = bool(args.split)
        targets.extend(
            collect_files(args.directory, ext, args.recursive, split_mode=to_split)
        )

    if not targets:
        print("❌ No files/folders found to process.")
        return

    start_all = time.time()
    done_paths: list[str] = []
    failed = 0

    for path in targets:
        # --------------------------------------------------------------
        # Split workflow
        # --------------------------------------------------------------
        if args.split:
            reason = split_skip_reason(path)
            if reason:
                print(f"⏭️ Skipping {path}: {reason}.")
                continue

            result = split_file(path, dry_run=args.dry_run, clean=args.clean)

        # --------------------------------------------------------------
        # Merge workflow
        # --------------------------------------------------------------
        else:   # args.merge
            reason = merge_skip_reason(path)
            if reason:
                print(f"⏭️ Skipping {path}: {reason}.")
                continue
            result = merge_file(path, dry_run=args.dry_run)

        if result:
            done_paths.append(result)
        else:
            failed += 1

    total_elapsed = format_elapsed_time(start_all)

    if args.dry_run:
        verb = "Would split" if args.split else "Would merge"
    else:
        verb = "Split" if args.split else "Merged"
    noun = "file(s)" if args.split else "folder(s)"

    print_banner("SUMMARY")
    for p in sorted(done_paths):
        print(f"✅ {p}")
    print(f"\n{verb} {len(done_paths)} {noun} in {total_elapsed}")
    if failed:
        print(f"❌ {failed} {noun} failed; see the messages above")
        sys.exit(1)


if __name__ == "__main__":
    main()
