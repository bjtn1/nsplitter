#!/usr/bin/env python3
"""
Tkinter GUI for the split/merge utility, themed with the Catppuccin‑Mocha
palette.
"""

from __future__ import annotations

import contextlib
import os
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from nsplitter import (
    collect_files,
    merge_file,
    merge_skip_reason,
    split_file,
    split_skip_reason,
)

# ----------------------------------------------------------------------
# ── Catppuccin Mocha colour palette
# ----------------------------------------------------------------------
MOCHA = {
    "base":      "#1E1E2E",   # surface0
    "mantle":    "#181825",   # mantle
    "crust":     "#11111B",   # crust
    "text":      "#CDD6F4",   # text
    "subtext0":  "#A6ADC8",   # subtext0
    "subtext1":  "#BAC2DE",   # subtext1
    "overlay0":  "#6C7086",   # overlay0
    "overlay1":  "#7F849C",   # overlay1
    "surface1":  "#313244",   # surface1
    "surface2":  "#45475A",   # surface2
    "blue":      "#89B4FA",
    "lavender":  "#B4BEFE",
    "sapphire":  "#74C7EC",
    "sky":       "#89DCEB",
    "teal":      "#94E2D5",
    "green":     "#A6E3A1",
    "yellow":    "#F9E2AF",
    "peach":     "#FAB387",
    "maroon":    "#EBA0AC",
    "red":       "#F38BA8",
    "mauve":     "#CBA6F7",
    "pink":      "#F5C2E7",
    "flamingo":  "#F2CDCD",
    "rosewater": "#F5E0DC",
}


# ----------------------------------------------------------------------
# ── Output capture
# ----------------------------------------------------------------------
class QueueWriter:
    """
    File-like object that forwards the core functions' ``print`` output to
    the UI thread.  Full lines go to the log; ``\\r``-terminated progress
    lines update the status label instead of flooding the log.
    """

    def __init__(self, q: queue.Queue):
        self.q = q
        self.buf = ""

    def write(self, text: str) -> int:
        self.buf += text
        while True:
            cut = min((i for i in (self.buf.find("\n"), self.buf.find("\r")) if i != -1),
                      default=-1)
            if cut == -1:
                break
            line, sep, self.buf = self.buf[:cut], self.buf[cut], self.buf[cut + 1:]
            if line.strip():
                self.q.put(("status" if sep == "\r" else "log", line))
        return len(text)

    def flush(self) -> None:
        if self.buf.strip():
            self.q.put(("log", self.buf))
        self.buf = ""


# ----------------------------------------------------------------------
# ── Main application
# ----------------------------------------------------------------------
class SplitMergeGUI(tk.Tk):
    def __init__(self):
        super().__init__()

        self.title("File Split / Merge")
        self.configure(bg=MOCHA["base"])
        self.minsize(640, 520)

        self.events: queue.Queue = queue.Queue()
        self.worker: threading.Thread | None = None

        self._style()
        self._layout()
        self._on_mode_change()

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(100, self._drain_events)

    # ------------------------------------------------------------------
    def _style(self):
        style = ttk.Style(self)
        style.theme_use("clam")          # a minimal theme we can recolour

        style.configure("TFrame", background=MOCHA["base"])
        style.configure("TLabel", background=MOCHA["base"], foreground=MOCHA["text"])
        style.configure("Status.TLabel", background=MOCHA["base"],
                        foreground=MOCHA["subtext0"])
        style.configure("TButton", background=MOCHA["surface1"],
                        foreground=MOCHA["text"], padding=5)
        style.map("TButton",
                  background=[("active", MOCHA["surface2"])],
                  foreground=[("disabled", MOCHA["overlay0"])])
        style.configure("Accent.TButton", background=MOCHA["blue"],
                        foreground=MOCHA["crust"])
        style.map("Accent.TButton",
                  background=[("active", MOCHA["lavender"]),
                              ("disabled", MOCHA["surface1"])],
                  foreground=[("disabled", MOCHA["overlay0"])])
        for widget in ("TRadiobutton", "TCheckbutton"):
            style.configure(widget, background=MOCHA["base"], foreground=MOCHA["text"])
            style.map(widget,
                      background=[("active", MOCHA["base"])],
                      foreground=[("disabled", MOCHA["overlay0"])])
        style.configure("TEntry", fieldbackground=MOCHA["crust"],
                        foreground=MOCHA["text"], insertcolor=MOCHA["text"])
        style.configure("TProgressbar", troughcolor=MOCHA["crust"],
                        background=MOCHA["blue"])

    # ------------------------------------------------------------------
    def _layout(self):
        pad = {"padx": 6, "pady": 4}
        root = ttk.Frame(self, padding=8)
        root.pack(fill=tk.BOTH, expand=True)
        root.columnconfigure(1, weight=1)
        root.rowconfigure(2, weight=1)
        root.rowconfigure(7, weight=1)

        # Mode selection
        ttk.Label(root, text="Mode:").grid(row=0, column=0, sticky="e", **pad)
        self.mode = tk.StringVar(value="split")
        modes = ttk.Frame(root)
        modes.grid(row=0, column=1, columnspan=3, sticky="w")
        for text, value in (("Split", "split"), ("Merge", "merge")):
            ttk.Radiobutton(modes, text=text, variable=self.mode, value=value,
                            command=self._on_mode_change).pack(side=tk.LEFT, padx=4)

        # Targets list
        self.targets_label = ttk.Label(root, text="Targets:")
        self.targets_label.grid(row=1, column=0, sticky="ne", **pad)
        self.targets = tk.Listbox(
            root, height=6, selectmode=tk.EXTENDED,
            bg=MOCHA["crust"], fg=MOCHA["text"],
            selectbackground=MOCHA["surface2"], selectforeground=MOCHA["text"],
            highlightthickness=0, borderwidth=0,
        )
        self.targets.grid(row=1, column=1, rowspan=2, sticky="nsew", **pad)

        buttons = ttk.Frame(root)
        buttons.grid(row=1, column=2, rowspan=2, sticky="n", **pad)
        self.btn_add = ttk.Button(buttons, text="Add…", command=self.browse)
        self.btn_add.pack(fill=tk.X, pady=2)
        self.btn_remove = ttk.Button(buttons, text="Remove", command=self.remove_selected)
        self.btn_remove.pack(fill=tk.X, pady=2)
        self.btn_clear = ttk.Button(buttons, text="Clear",
                                    command=lambda: self.targets.delete(0, tk.END))
        self.btn_clear.pack(fill=tk.X, pady=2)

        # Folder scan: fills the targets list using collect_files
        ttk.Label(root, text="Scan folder:").grid(row=3, column=0, sticky="e", **pad)
        scan = ttk.Frame(root)
        scan.grid(row=3, column=1, columnspan=2, sticky="we")
        scan.columnconfigure(0, weight=1)
        self.scan_dir = tk.StringVar()
        ttk.Entry(scan, textvariable=self.scan_dir).grid(row=0, column=0, sticky="we", padx=(6, 4))
        ttk.Button(scan, text="Browse…", command=self.browse_scan_dir)\
            .grid(row=0, column=1, padx=2)

        scan_opts = ttk.Frame(root)
        scan_opts.grid(row=4, column=1, columnspan=2, sticky="w")
        ttk.Label(scan_opts, text="Extension:").pack(side=tk.LEFT, padx=(6, 4))
        self.ext_var = tk.StringVar(value="nsp")
        ttk.Entry(scan_opts, textvariable=self.ext_var, width=8).pack(side=tk.LEFT)
        self.recursive = tk.BooleanVar()
        ttk.Checkbutton(scan_opts, text="Recursive", variable=self.recursive)\
            .pack(side=tk.LEFT, padx=8)
        self.btn_scan = ttk.Button(scan_opts, text="Scan", command=self.scan)
        self.btn_scan.pack(side=tk.LEFT, padx=4)

        # Options
        opts = ttk.Frame(root)
        opts.grid(row=5, column=1, columnspan=2, sticky="w", pady=(8, 0))
        self.dryrun = tk.BooleanVar()
        ttk.Checkbutton(opts, text="Dry‑run", variable=self.dryrun)\
            .pack(side=tk.LEFT, padx=6)
        self.clean = tk.BooleanVar()
        self.chk_clean = ttk.Checkbutton(opts, text="Clean (delete originals)",
                                         variable=self.clean)
        self.chk_clean.pack(side=tk.LEFT, padx=6)

        # Start button + progress
        self.btn_start = ttk.Button(root, text="Start", style="Accent.TButton",
                                    command=self.start)
        self.btn_start.grid(row=6, column=0, sticky="w", **pad)
        self.progress = ttk.Progressbar(root, mode="determinate")
        self.progress.grid(row=6, column=1, columnspan=2, sticky="we", **pad)

        # Log area (plain Text widget – coloured manually)
        log_frame = ttk.Frame(root)
        log_frame.grid(row=7, column=0, columnspan=3, sticky="nsew", **pad)
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        self.log = tk.Text(log_frame, height=12, bg=MOCHA["crust"],
                           fg=MOCHA["text"], insertbackground=MOCHA["text"],
                           borderwidth=0, highlightthickness=0,
                           wrap=tk.WORD, state=tk.DISABLED)
        self.log.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(log_frame, command=self.log.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.log.configure(yscrollcommand=scroll.set)
        for tag, colour in (("ok", "green"), ("error", "red"),
                            ("skip", "yellow"), ("info", "subtext1")):
            self.log.tag_configure(tag, foreground=MOCHA[colour])

        self.status = ttk.Label(root, text="Ready", style="Status.TLabel")
        self.status.grid(row=8, column=0, columnspan=3, sticky="w", **pad)

    # ------------------------------------------------------------------
    # ── UI helpers (main thread only)
    # ------------------------------------------------------------------
    def _on_mode_change(self):
        split = self.mode.get() == "split"
        self.targets_label.configure(text="Files:" if split else "Split folders:")
        self.chk_clean.state(["!disabled"] if split else ["disabled"])
        if not split:
            self.clean.set(False)
        self.targets.delete(0, tk.END)

    def _add_targets(self, paths):
        existing = set(self.targets.get(0, tk.END))
        for p in paths:
            p = os.path.normpath(p)
            if p not in existing:
                self.targets.insert(tk.END, p)
                existing.add(p)

    def browse(self):
        """Open file/folder chooser depending on mode."""
        if self.mode.get() == "split":
            paths = filedialog.askopenfilenames(title="Select file(s) to split")
        else:
            folder = filedialog.askdirectory(title="Select split folder")
            paths = (folder,) if folder else ()
        self._add_targets(paths)

    def browse_scan_dir(self):
        folder = filedialog.askdirectory(title="Select folder to scan")
        if folder:
            self.scan_dir.set(folder)

    def remove_selected(self):
        for index in reversed(self.targets.curselection()):
            self.targets.delete(index)

    def scan(self):
        folder = self.scan_dir.get().strip()
        ext = self.ext_var.get().strip().lstrip(".")
        if not os.path.isdir(folder):
            messagebox.showwarning("Scan", "Choose a folder to scan first.")
            return
        if not ext:
            messagebox.showwarning("Scan", "Enter a file extension, e.g. nsp.")
            return
        found = collect_files(folder, ext, self.recursive.get(),
                              split_mode=self.mode.get() == "split")
        self._add_targets(found)
        self.log_msg(f"ℹ️ Scan found {len(found)} match(es) in {folder}", "info")

    def log_msg(self, msg: str, tag: str | None = None):
        if tag is None:
            tag = ("ok" if msg.startswith("✅") else
                   "error" if msg.startswith("❌") else
                   "skip" if msg.startswith(("⏭", "⚠")) else "info")
        self.log.configure(state=tk.NORMAL)
        self.log.insert(tk.END, msg + "\n", tag)
        self.log.see(tk.END)
        self.log.configure(state=tk.DISABLED)

    def _set_running(self, running: bool):
        state = ["disabled"] if running else ["!disabled"]
        for w in (self.btn_start, self.btn_add, self.btn_remove,
                  self.btn_clear, self.btn_scan):
            w.state(state)

    # ------------------------------------------------------------------
    def start(self):
        targets = list(self.targets.get(0, tk.END))
        if not targets:
            messagebox.showwarning("No target", "Add at least one file/folder.")
            return

        mode = self.mode.get()
        dry = self.dryrun.get()
        clean = self.clean.get() and mode == "split"
        if clean and not dry and not messagebox.askyesno(
                "Delete originals?",
                "Each original file will be deleted after its parts are "
                "verified. Continue?"):
            return

        self._set_running(True)
        self.progress.configure(maximum=len(targets), value=0)
        self.status.configure(text="Working…")
        self.worker = threading.Thread(
            target=self.process, args=(targets, mode, dry, clean), daemon=True)
        self.worker.start()

    # ------------------------------------------------------------------
    # ── Worker thread: never touches widgets, only posts to self.events
    # ------------------------------------------------------------------
    def process(self, targets, mode, dry, clean):
        post = self.events.put
        writer = QueueWriter(self.events)
        done = failed = skipped = 0

        for i, path in enumerate(targets):
            name = os.path.basename(path)
            try:
                if mode == "split":
                    reason = split_skip_reason(path)
                else:
                    reason = merge_skip_reason(path)

                if reason:
                    post(("log", f"⏭️ Skipping {name}: {reason}"))
                    skipped += 1
                else:
                    post(("status", f"{'Splitting' if mode == 'split' else 'Merging'} {name}…"))
                    with contextlib.redirect_stdout(writer):
                        if mode == "split":
                            result = split_file(path, dry_run=dry, clean=clean)
                        else:
                            result = merge_file(path, dry_run=dry)
                    writer.flush()
                    if result:
                        done += 1
                    else:
                        failed += 1
            except Exception as e:      # keep going with the next target
                writer.flush()
                post(("log", f"❌ {name}: {e}"))
                failed += 1
            post(("progress", i + 1))

        post(("finished", (done, failed, skipped, mode, dry)))

    # ------------------------------------------------------------------
    def _drain_events(self):
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "log":
                    self.log_msg(payload)
                elif kind == "status":
                    self.status.configure(text=payload)
                elif kind == "progress":
                    self.progress.configure(value=payload)
                elif kind == "finished":
                    self._finished(*payload)
        except queue.Empty:
            pass
        self.after(100, self._drain_events)

    def _finished(self, done, failed, skipped, mode, dry):
        verb = ("Would split" if dry else "Split") if mode == "split" \
            else ("Would merge" if dry else "Merged")
        summary = f"{verb} {done}, failed {failed}, skipped {skipped}"
        self.log_msg(("❌ " if failed else "✅ ") + summary)
        self.status.configure(text=summary)
        self._set_running(False)
        self.worker = None
        if failed:
            messagebox.showerror("Finished with errors",
                                 f"{summary}.\nSee the log for details.")

    def _on_close(self):
        if self.worker and self.worker.is_alive() and not messagebox.askyesno(
                "Quit?",
                "An operation is still running. Quitting now can leave a "
                "half-written file. Quit anyway?"):
            return
        self.destroy()


if __name__ == "__main__":
    app = SplitMergeGUI()
    app.mainloop()
