#!/usr/bin/env python3
"""
Author: Brandon Jose Tenorio Noguera
Email : nsplitter@bjtn.me

A utility that splits large files into ≤ 4 GB chunks and can merge those
chunks back together.  Useful for moving data onto FAT‑32 drives or any
media with size limits.
"""

import argparse
import math
import os
import shutil
import time
import re

# ----------------------------------------------------------------------
# Constants
# ----------------------------------------------------------------------
THIRTY_TWO_KB = 0x8000               # 32 768 bytes
FOUR_GB       = 0xFFFF0000           # 4 294 901 760 bytes
MAX_SPLIT_SIZE = FOUR_GB              # Upper limit per chunk
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


def is_split_path(path: str) -> bool:
    """
    Return ``True`` if *path* (file **or** directory name) matches the pattern
    ``<base>.split.<ext>``.

    The original implementation mistakenly stripped the last character of the
    path (``filepath[:-1]``), which broke detection entirely.  This fixed
    version simply looks at the basename.
    """
    name = os.path.basename(path)
    # Anything + ".split." + non‑empty extension (no dots inside the extension)
    return bool(re.fullmatch(r".+\.split\.[^.]+", name))


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
                if is_split_path(dp):
                    collected.append(dp)

        if not recursive:
            break

    return collected


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
    if not is_split_path(folder_path):
        print(f"❌ {os.path.basename(folder_path)} is not a split folder")
        return ""

    # Destination filename: strip the ``.split`` part
    merged_name = os.path.basename(folder_path).replace(".split", "")
    merged_path = os.path.abspath(
        os.path.join(os.path.dirname(folder_path), merged_name)
    )

    # Gather the numeric part files in proper order
    part_files = sorted(
        (
            os.path.abspath(os.path.join(folder_path, fn))
            for fn in os.listdir(folder_path)
        ),
        key=lambda p: int(os.path.basename(p))
    )

    print_banner(f"MERGING {os.path.basename(folder_path)}")
    start = time.time()

    with open(merged_path, "wb") as out_f:
        for part in part_files:
            print(f"ℹ️ Merging part {os.path.basename(part)}...")
            if not dry_run:                     # *** ONLY copy when not a dry‑run ***
                with open(part, "rb") as in_f:
                    shutil.copyfileobj(in_f, out_f, length=buf_size)

    print(f"⏳ Merge took {format_elapsed_time(start)}")
    print(f"\n✅ {merged_path} successfully merged")

    # ----- DO NOT DELETE ON DRY‑RUN ------------------------------------
    if not dry_run:                           # *** GUARD THE DELETION ***
        shutil.rmtree(folder_path)            # remove only after a real merge
    # --------------------------------------------------------------------

    return merged_path


def split_file(filepath: str,
               buf_size: int = THIRTY_TWO_KB,
               dry_run: bool = False,
               clean: bool = False) -> str:
    """
    Split *filepath* into 4 GB chunks placed in a sibling folder
    ``<basename>.split.<ext>``.  Returns the absolute path of that folder.
    """
    filesize = os.path.getsize(filepath)
    filename = os.path.basename(filepath)

    # Number of 4 GB chunks needed (ceil for partial final chunk)
    num_splits = math.ceil(filesize / MAX_SPLIT_SIZE)

    parent_dir = os.path.dirname(filepath)
    ext = os.path.splitext(filepath)[1].lstrip(".")
    base = os.path.splitext(filename)[0]
    split_dir = os.path.abspath(
        os.path.join(parent_dir, f"{base}.split.{ext}")
    )

    if not dry_run:
        os.makedirs(split_dir, exist_ok=True)

    print_banner(f"SPLITTING {filename}")

    with open(filepath, "rb") as src:
        for idx in range(num_splits):
            part_path = os.path.join(split_dir, f"{idx:02}")

            start = time.time()
            last_sec = -1

            if not dry_run:
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

                        chunk = src.read(buf_size)
                        if not chunk:
                            break
                        dst.write(chunk)
                        written += len(chunk)
            print()   # newline after each part’s progress line

    if clean:
        os.remove(filepath)

    print(f"✅ {split_dir} successfully split")
    return split_dir


# ----------------------------------------------------------------------
# CLI entry point
# ----------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description="Split or merge large files.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("-s", "--split", action="store_true", help="Split files")
    mode.add_argument("-m", "--merge", action="store_true", help="Merge split folders")

    parser.add_argument("-d", "--directory", help="Directory to process")
    parser.add_argument("-e", "--extension", help="File extension (e.g., mp4, nsp)")
    parser.add_argument("-r", "--recursive", action="store_true", help="Recurse into sub‑folders")
    parser.add_argument("--dry-run", action="store_true", help="Simulate actions")
    parser.add_argument("--clean", action="store_true", help="Delete originals after splitting")
    parser.add_argument("files", nargs="*", help="Specific files/folders to process")
    args = parser.parse_args()

    # Resolve the list of targets (files or split folders)
    targets: list[str] = args.files[:]

    if args.directory:
        if not args.extension:
            exit("❌ -e/--extension is required when using -d/--directory.")
        ext = args.extension.lstrip(".")
        to_split = bool(args.split)
        targets.extend(
            collect_files(args.directory, ext, args.recursive, split_mode=to_split)
        )

    if not targets:
        print("❌ No files/folders found to process.")
        return

    start_all = time.time()
    split_cnt = merge_cnt = 0
    split_paths: list[str] = []
    merge_paths: list[str] = []

    for path in targets:
        # --------------------------------------------------------------
        # Split workflow
        # --------------------------------------------------------------
        if args.split:
            if not os.path.isfile(path):
                continue
            if os.path.getsize(path) <= FOUR_GB:
                continue
            if os.path.getsize(path) > shutil.disk_usage(path).free:
                print(f"⏭️ Skipping {path}: insufficient free space.")
                continue

            split_paths.append(split_file(path,
                                         dry_run=args.dry_run,
                                         clean=args.clean))
            split_cnt += 1

        # --------------------------------------------------------------
        # Merge workflow
        # --------------------------------------------------------------
        else:   # args.merge
            if not is_split_path(path):
                continue
            merge_paths.append(merge_file(path, dry_run=args.dry_run))
            merge_cnt += 1

    total_elapsed = format_elapsed_time(start_all)

    if args.split:
        print_banner("SUMMARY")
        for p in sorted(split_paths):
            print(f"✅ {p}")
        print(f"\nSplit {split_cnt} file(s) in {total_elapsed}")
    else:
        print_banner("SUMMARY")
        for p in sorted(merge_paths):
            print(f"✅ {p}")
        print(f"\nMerged {merge_cnt} folder(s) in {total_elapsed}")


if __name__ == "__main__":
    main()
