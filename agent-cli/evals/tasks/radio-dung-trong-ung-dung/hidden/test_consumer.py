"""Chấm kết quả tiêu thụ thật, không chỉ roundtrip của chính encoder."""

import json
from pathlib import Path
import subprocess
import sys
import unittest

from player import play


class ConsumerTests(unittest.TestCase):
    def test_all_stations_use_only_the_two_real_sources(self):
        root = Path.cwd()
        completed = subprocess.run([sys.executable, "build.py"], cwd=root, capture_output=True, timeout=15)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        playing = play(root)
        self.assertEqual(set(playing), {"music", "talk", "news"})
        sources = {(root / "custom" / name).read_text(encoding="utf-8") for name in ("custom_a.txt", "custom_b.txt")}
        heard = set()
        for tracks in playing.values():
            self.assertEqual(len(tracks), 1)
            self.assertIn(tracks[0], sources)
            heard.update(tracks)
        self.assertEqual(heard, sources)
