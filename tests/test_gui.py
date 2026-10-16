"""Tests for the GUI's output capture (no window needed)."""

import os
import queue
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import nsplitter_gui
except ImportError:          # tkinter missing, e.g. minimal Linux Python
    nsplitter_gui = None


@unittest.skipIf(nsplitter_gui is None, "tkinter not available")
class QueueWriterTests(unittest.TestCase):
    def setUp(self):
        self.q = queue.Queue()
        self.writer = nsplitter_gui.QueueWriter(self.q)

    def drain(self):
        items = []
        while not self.q.empty():
            items.append(self.q.get_nowait())
        return items

    def test_lines_go_to_log(self):
        print("== SPLITTING a ==\n\n✅ done", file=self.writer)
        self.assertEqual(self.drain(), [("log", "== SPLITTING a =="), ("log", "✅ done")])

    def test_carriage_return_goes_to_status(self):
        self.writer.write("ℹ️ Splitting part 00... Elapsed: 00:00:01\r")
        self.writer.write("ℹ️ Splitting part 00... Elapsed: 00:00:02\r")
        self.writer.write("\n")
        self.assertEqual(self.drain(), [
            ("status", "ℹ️ Splitting part 00... Elapsed: 00:00:01"),
            ("status", "ℹ️ Splitting part 00... Elapsed: 00:00:02"),
        ])

    def test_partial_line_waits_for_flush(self):
        self.writer.write("half a ")
        self.assertEqual(self.drain(), [])
        self.writer.write("line")
        self.writer.flush()
        self.assertEqual(self.drain(), [("log", "half a line")])


if __name__ == "__main__":
    unittest.main()
