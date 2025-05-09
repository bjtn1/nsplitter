"""
@author: Brandon Jose Tenorio Noguera
@email: nsplitter@bjtn.me

Contains the core functions and logic needed for the nsplitter CLI to work such as (but not limited to):
- collect_files(directory, extension, recursive)
- split_file(filepath, filename, filesize)
- format_elapsed_time(start_time)
"""

import math
import os
import time

ONE_KB = 2**10
THIRTY_TWO_KB = 32 * ONE_KB
SIXTY_FOUR_KB = 64 * ONE_KB
ONE_MB = 2**20
FOUR_GB = 4 * 2**30
MAX_SPLIT_SIZE = FOUR_GB - SIXTY_FOUR_KB


def format_elapsed_time(start_time: float) -> str:
    """
    Returns the formatted elapsed time since the given start time.

    Args:
        start_time (float): The starting time in seconds since the epoch (as returned by time.time()).

    Returns:
        str: Elapsed time formatted as "HH:MM:SS".
    """
    elapsed_seconds = time.time() - start_time
    return time.strftime("%H:%M:%S", time.gmtime(elapsed_seconds))


def split_file(filepath: str, filesize: int, buf_size: int = THIRTY_TWO_KB) -> str:
    """
    Splits a large file into multiple 4GB chunks and stores them in a dedicated split directory.

    The output files are named numerically (e.g., 00, 01, 02...) and stored in a new directory
    located next to the original file, named <filename>.split. The original file is deleted
    after splitting is completed.

    Args:
        filepath (str): The full path to the file to be split.
        filesize (int): The size of the file in bytes.
        bufsize  (int): The size of the buffer where we store bytes to be read and written

    Returns:
        str: Path of the newly created split directory
    """

    # get the name of the file from the filepath
    filename: str = os.path.basename(filepath)

    # calculate how many splits we're gonna create for this file
    # use math.ceil to in case filesize is not perfectly divisible by 4GB
    num_splits = math.ceil(filesize / MAX_SPLIT_SIZE)

    # get the name of the directory where this file is located
    # so that we know where to put the split files
    parent_dir = os.path.dirname(filepath)

    # creates a file named <filename>.split.<file_extension>
    file_extension = os.path.splitext(filepath)[1].lstrip(".")
    filename_without_extension = os.path.splitext(os.path.basename(filepath))[0]
    split_dir = os.path.join(parent_dir, f"{filename_without_extension}.split.{file_extension}")
    os.makedirs(split_dir, exist_ok=True)

    start_time = time.time()

    # needed for progress report what is this for?
    total_bytes_written = 0

    # open file in read-binary mode
    with open(filepath, "rb") as infile:
        # run this loop for as many splits as will be needed for this specific file
        for split in range(num_splits):
            # create and name the split file {filename}/{nn} where nn is the split number beginnign at 00
            split_path = os.path.join(split_dir, f"{split:02}")
            # begin loop to write to the newly created split file
            with open(split_path, "wb") as outfile:
                bytes_written = 0
                # each split must be 4GB - 64KB long
                while bytes_written < (MAX_SPLIT_SIZE):
                    # read the input file (file to be split) in chunks of 32KB 
                    chunk = infile.read(buf_size)
                    # if there is no more bytes to be read, break out of the loop
                    if not chunk:
                        break
                    # write the 32KB chunk we just read fromn the infile to the outfile
                    outfile.write(chunk)
                    # increment loop-stopping condition
                    bytes_written += len(chunk)
                    # this is just a fun metric to display once the process has finished
                    total_bytes_written += len(chunk)

            elapsed_time = format_elapsed_time(start_time)
            # get the progress of the splitting process for every file after each split
            progress = total_bytes_written / filesize
            # print report for each split
            print(
                f"[{elapsed_time}] [{split + 1}/{num_splits}] "
                f"[{progress:.2%}] {total_bytes_written:_}/{filesize:_} bytes | {filename}",
                end="\r" if total_bytes_written < filesize else "\n",
            )

    # remove the file that was just split
    # os.remove(filepath)

    # return the path of the newly created .split directory
    return split_dir

def collect_files(directory: str, extension: str, recursive: bool) -> list[str]:
    """
    Collects all files with a given extension from a directory.

    Args:
        directory (str): Path to the directory to search.
        extension (str): File extension to match (e.g., ".mp4").
        recursive (bool): Whether to search subdirectories recursively.

    Returns:
        list[str]: A list of file paths matching the given extension.
    """
    collected_files: list[str] = []
    for root, _, files in os.walk(directory):
        for file in files:
            if file.endswith(extension):
                collected_files.append(os.path.join(root, file))
        if not recursive:
            break
    return collected_files
