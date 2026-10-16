"""
Regression tests for nsplitter.  Run with:  python -m unittest discover tests

Chunk and FAT32 limits are shrunk to 64 KiB so the tests run on small files.
"""

import contextlib
import io
import os
import stat
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import nsplitter  # noqa: E402

LIMIT = 0x10000


class NsplitterTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        for name, value in (("MAX_SPLIT_SIZE", LIMIT),
                            ("FAT32_MAX_FILE_SIZE", LIMIT)):
            patcher = mock.patch.object(nsplitter, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def tearDown(self):
        self.tmp.cleanup()

    def make_file(self, name="game.nsp", size=LIMIT * 2 + 5):
        path = os.path.join(self.dir, name)
        self.data = os.urandom(size)
        with open(path, "wb") as f:
            f.write(self.data)
        return path

    def run_cli(self, *argv):
        out = io.StringIO()
        with mock.patch.object(sys, "argv", ["nsplitter.py", *argv]), \
                contextlib.redirect_stdout(out):
            try:
                nsplitter.main()
                code = 0
            except SystemExit as e:
                code = e.code
        return code, out.getvalue()

    def split_dir(self, name="game.split.nsp"):
        return os.path.join(self.dir, name)


class DryRunTests(NsplitterTestCase):
    def test_dry_run_clean_keeps_original(self):
        path = self.make_file()
        self.run_cli("-s", "--dry-run", "--clean", path)
        self.assertTrue(os.path.exists(path))
        self.assertFalse(os.path.exists(self.split_dir()))

    def test_dry_run_merge_does_not_touch_files(self):
        path = self.make_file()
        self.run_cli("-s", "--clean", path)
        self.run_cli("-m", "--dry-run", self.split_dir())
        self.assertFalse(os.path.exists(path))
        self.assertTrue(os.path.isdir(self.split_dir()))

    def test_merge_refuses_to_overwrite_existing_file(self):
        path = self.make_file()
        self.run_cli("-s", path)            # original kept
        code, _ = self.run_cli("-m", self.split_dir())
        self.assertEqual(code, 1)
        with open(path, "rb") as f:
            self.assertEqual(f.read(), self.data)
        self.assertTrue(os.path.isdir(self.split_dir()))


class SplitTests(NsplitterTestCase):
    def test_round_trip(self):
        path = self.make_file(size=LIMIT * 3 + 123)
        self.run_cli("-s", "--clean", path)
        self.assertEqual(sorted(os.listdir(self.split_dir())), ["00", "01", "02", "03"])
        self.run_cli("-m", self.split_dir())
        with open(path, "rb") as f:
            self.assertEqual(f.read(), self.data)
        self.assertFalse(os.path.exists(self.split_dir()))

    def test_parts_never_exceed_limit_with_odd_buffer(self):
        path = self.make_file(size=LIMIT * 3)
        with contextlib.redirect_stdout(io.StringIO()):
            out = nsplitter.split_file(path, buf_size=0x6000)
        sizes = [os.path.getsize(os.path.join(out, p)) for p in sorted(os.listdir(out))]
        self.assertEqual(sizes, [LIMIT, LIMIT, LIMIT])

    def test_refuses_non_empty_existing_split_folder(self):
        path = self.make_file()
        os.makedirs(self.split_dir())
        open(os.path.join(self.split_dir(), "03"), "wb").close()
        code, _ = self.run_cli("-s", "--clean", path)
        self.assertEqual(code, 1)
        self.assertTrue(os.path.exists(path))
        self.assertEqual(os.listdir(self.split_dir()), ["03"])

    def test_file_at_fat32_limit_is_not_split(self):
        path = self.make_file(size=LIMIT)
        self.run_cli("-s", path)
        self.assertFalse(os.path.exists(self.split_dir()))

    @unittest.skipUnless(os.name == "nt", "archive bit check uses Windows attributes")
    def test_split_folder_has_archive_bit(self):
        path = self.make_file()
        self.run_cli("-s", path)
        attrs = os.stat(self.split_dir()).st_file_attributes
        self.assertTrue(attrs & stat.FILE_ATTRIBUTE_ARCHIVE)


class MergeTests(NsplitterTestCase):
    def split_and_clean(self, name="game.nsp"):
        path = self.make_file(name)
        self.run_cli("-s", "--clean", path)
        return path

    def test_trailing_slash(self):
        path = self.split_and_clean()
        self.run_cli("-m", self.split_dir() + os.sep)
        self.assertTrue(os.path.exists(path))

    @unittest.skipUnless(os.name == "nt", "Windows command-line quoting")
    def test_stray_quote_from_quoted_trailing_backslash(self):
        # cmd/PowerShell turn "C:\a b\x.split.nsp\" into ...x.split.nsp"
        path = self.split_and_clean()
        self.run_cli("-m", self.split_dir() + '"')
        self.assertTrue(os.path.exists(path))

    def test_ignores_os_junk_files(self):
        path = self.split_and_clean()
        for junk in ("._00", ".DS_Store", "desktop.ini"):
            open(os.path.join(self.split_dir(), junk), "wb").close()
        self.run_cli("-m", self.split_dir())
        with open(path, "rb") as f:
            self.assertEqual(f.read(), self.data)

    def test_refuses_missing_part(self):
        path = self.split_and_clean()
        os.remove(os.path.join(self.split_dir(), "01"))
        code, out = self.run_cli("-m", self.split_dir())
        self.assertEqual(code, 1)
        self.assertIn("missing part(s) 01", out)
        self.assertFalse(os.path.exists(path))
        self.assertTrue(os.path.isdir(self.split_dir()))

    def test_only_final_split_is_stripped(self):
        self.split_and_clean("a.splitter.nsp")
        self.run_cli("-m", self.split_dir("a.splitter.split.nsp"))
        self.assertEqual(os.listdir(self.dir), ["a.splitter.nsp"])

    def test_file_without_extension_round_trips(self):
        path = self.make_file("backup")
        self.run_cli("-s", "--clean", path)
        self.assertEqual(os.listdir(self.dir), ["backup.split"])
        self.run_cli("-m", self.split_dir("backup.split"))
        with open(path, "rb") as f:
            self.assertEqual(f.read(), self.data)

    def test_missing_directory_is_an_error(self):
        code, out = self.run_cli("-s", "-d", os.path.join(self.dir, "nope"), "-e", "nsp")
        self.assertIn("is not a directory", str(code) + out)
        self.assertNotEqual(code, 0)

    def test_directory_merge_honours_extension(self):
        self.split_and_clean("game.nsp")
        self.split_and_clean("movie.mp4")
        self.run_cli("-m", "-d", self.dir, "-e", "nsp")
        self.assertEqual(sorted(os.listdir(self.dir)), ["game.nsp", "movie.split.mp4"])


if __name__ == "__main__":
    unittest.main()
