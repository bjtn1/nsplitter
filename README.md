<!-- TOC start (generated with https://github.com/derlin/bitdowntoc) -->

<!-- TOC --><a name="nsplitter"></a>
# nsplitter

**Split and merge large files for FAT32 compatibility**

`nsplitter.py` is a command-line utility that splits large files into smaller chunks (e.g., 4GB) and merges them back. It’s particularly useful for transferring large files onto FAT32-formatted drives, which cannot store files larger than 4GB.

> Split algorithm inspired by [AnalogMan151/splitNSP](https://github.com/AnalogMan151/splitNSP/blob/master/splitNSP.py).

---

* [🚀 Features](#-features)
* [📦 Installation](#-installation)
* [🧑‍💻 Usage](#-usage)
  + [Split a single file](#split-a-single-file)
  + [Merge a previously split folder](#merge-a-previously-split-folder)
  + [Split all `.nsp` files in a folder (non-recursive)](#split-all-nsp-files-in-a-folder-non-recursive)
  + [Merge all split folders in a folder recursively](#merge-all-split-folders-in-a-folder-recursively)
  + [Dry-run mode (simulate actions without modifying files)](#dry-run-mode-simulate-actions-without-modifying-files)
* [⚙️ Command-Line Options](#-command-line-options)
* [📁 Output](#-output)
* [🛑 Limitations](#-limitations)
* [🧼 Example Folder Structure](#-example-folder-structure)
* [🤝 Contributions](#-contributions)
* [💬 Contact](#-contact)

<!-- TOC end -->

---

<!-- TOC --><a name="-features"></a>
## 🚀 Features

- 🔹 Split any large file into 4GB chunks (FAT32-friendly)
- 🔹 Merge split folders back into the original file
- 🔹 Optional dry-run mode for safe testing
- 🔹 Supports individual files or entire directories (with optional recursion)
- 🔹 Sets the FAT archive bit so the Switch reads a split folder as one file
- 🔹 Checks part sizes before deleting anything
- 🔹 CLI output with progress banners and a summary

---

<!-- TOC --><a name="-installation"></a>
## 📦 Installation

```bash
git clone https://github.com/bjtn1/nsplitter.git
cd nsplitter
python3 nsplitter.py --help
```

> Requires Python 3.7+

### GUI

```bash
python3 nsplitter_gui.py
```

Pick **Split** or **Merge**, add files (or split folders) with **Add…**, or fill the list by scanning a folder for an extension, optionally recursively. Dry-run and Clean work as on the command line, and the log shows each result. The GUI needs Tkinter, which ships with Python on Windows and macOS; on Debian/Ubuntu install `python3-tk`.

---

<!-- TOC --><a name="-usage"></a>
## 🧑‍💻 Usage

<!-- TOC --><a name="split-a-single-file"></a>
### Split a single file

```bash
python3 nsplitter.py -s path/to/largefile.nsp
```

<!-- TOC --><a name="merge-a-previously-split-folder"></a>
### Merge a previously split folder

```bash
python3 nsplitter.py -m path/to/largefile.split.nsp
```

<!-- TOC --><a name="split-all-nsp-files-in-a-folder-non-recursive"></a>
### Split all `.nsp` files in a folder (non-recursive)

```bash
python3 nsplitter.py -s -d path/to/folder -e nsp
```

<!-- TOC --><a name="merge-all-split-folders-in-a-folder-recursively"></a>
### Merge all split folders in a folder recursively

```bash
python3 nsplitter.py -m -d path/to/folder -e nsp -r
```

<!-- TOC --><a name="dry-run-mode-simulate-actions-without-modifying-files"></a>
### Dry-run mode (simulate actions without modifying files)

```bash
python3 nsplitter.py -s -d path/to/folder -e nsp --dry-run
```

---

<!-- TOC --><a name="-command-line-options"></a>
## ⚙️ Command-Line Options

| Flag              | Description                                                   |
|-------------------|---------------------------------------------------------------|
| `-s`, `--split`    | Split files                                                   |
| `-m`, `--merge`    | Merge previously split files                                  |
| `-d`, `--directory`| Directory to search for files                                 |
| `-e`, `--extension`| File extension to target (e.g., `nsp`, `mp4`)                |
| `-r`, `--recursive`| Recurse into subdirectories                                   |
| `--dry-run`        | Simulate the process without making changes                  |
| `--clean`          | Delete the original file after a successful split            |
| `files`            | One or more individual files/folders to process              |

> Note: When using `--directory`, `--extension` is required. When merging, it selects split folders with that extension (e.g. `-e nsp` matches `*.split.nsp`).

---

<!-- TOC --><a name="-output"></a>
## 📁 Output

- When splitting: creates a folder named `filename.split.extension` next to the original, containing numbered parts (`00`, `01`, `02`, ...) of at most 4 GiB - 64 KiB each, and sets the folder's archive bit. With `--clean`, the original is deleted only after the parts are checked.
- When merging: combines parts back into a single file, checks its size, and removes the `.split` folder. It refuses to overwrite an existing file with the same name.

---

<!-- TOC --><a name="-limitations"></a>
## 🛑 Limitations

- Files that already fit on FAT32 (≤ 4 GiB - 1 byte) are skipped during splitting.
- The system must have enough free disk space for the parts (when splitting) or the merged file (when merging).
- Only numeric part names are supported (e.g., `00`, `01`, ...); other files in a split folder are ignored.
- Splitting refuses to write into an existing split folder that isn't empty.
- The archive bit is set automatically on Windows, and on Linux when `fatattr` is installed. Elsewhere, set it yourself on the split folder, or the Switch will treat it as a plain folder.

---

<!-- TOC --><a name="-example-folder-structure"></a>
## 🧼 Example Folder Structure

After splitting:

```
game.nsp            (deleted if --clean was used)
game.split.nsp/
├── 00
├── 01
└── 02
```

---

<!-- TOC --><a name="-contributions"></a>
## 🤝 Contributions

Pull requests are welcome! Please open an issue first if you’d like to discuss a major change.

Run the tests with `python3 -m unittest discover tests`.

---

<!-- TOC --><a name="-contact"></a>
## 💬 Contact

Questions or feedback?  
📧 [nsplitter@bjtn.me](mailto:nsplitter@bjtn.me)
