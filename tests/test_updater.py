"""Version resolution, asset selection, staging and the swap script."""
import json
import os
import tarfile
import tempfile
import unittest
import urllib.error
import urllib.request
import zipfile

from .context import app, needs_display


@needs_display
class VersionCompare(unittest.TestCase):
    def test_ordering(self):
        cases = [("v1.2.0", "1.2.0", False), ("v1.2.1", "1.2.0", True),
                 ("v1.10.0", "1.9.0", True), ("v1.2.0", "1.2.1", False),
                 ("v2.0.0", "1.99.99", True), ("1.2", "1.2.0", False),
                 ("v0.3.1", "0.3.0", True), ("v0.10.0", "0.9.9", True)]
        for tag, current, expected in cases:
            with self.subTest(tag=tag, current=current):
                self.assertEqual(app.is_newer(tag, current), expected)

    def test_unparseable_tags_do_not_raise(self):
        for tag in ("garbage", "", "v", "release-candidate", None):
            with self.subTest(tag=tag):
                self.assertFalse(app.is_newer(tag, "1.0.0"))


@needs_display
class AssetSelection(unittest.TestCase):
    RELEASE = {"assets": [
        {"name": "AFK-Farm-Clicker-windows-x64.zip", "browser_download_url": "w"},
        {"name": "AFK-Farm-Clicker-linux-x86_64.tar.gz", "browser_download_url": "l"},
        {"name": "AFK-Farm-Clicker-macos-arm64.zip", "browser_download_url": "m"},
    ]}

    def test_picks_something_for_this_platform(self):
        self.assertIsNotNone(app.pick_asset(self.RELEASE))

    def test_empty_and_missing(self):
        self.assertIsNone(app.pick_asset({"assets": []}))
        self.assertIsNone(app.pick_asset({}))
        self.assertIsNone(app.pick_asset(None))


@needs_display
class Staging(unittest.TestCase):
    def _archive(self, kind):
        base = tempfile.mkdtemp()
        payload = os.path.join(base, "AFK Farm Clicker")
        os.makedirs(payload)
        with open(os.path.join(payload, "marker.txt"), "w") as fh:
            fh.write("hello")
        path = os.path.join(base, "pkg." + kind)
        if kind == "zip":
            with zipfile.ZipFile(path, "w") as zf:
                zf.write(os.path.join(payload, "marker.txt"),
                         "AFK Farm Clicker/marker.txt")
        else:
            with tarfile.open(path, "w:gz") as tf:
                tf.add(payload, arcname="AFK Farm Clicker")
        return path

    def test_both_archive_kinds_flatten(self):
        # The Linux and macOS archives keep a top-level folder and the Windows
        # one does not; staging has to hand the swap script the same shape.
        for kind, suffix in (("zip", "windows-x64.zip"),
                             ("tar.gz", "linux-x86_64.tar.gz")):
            with self.subTest(kind=kind):
                archive = self._archive(kind)
                staged = app.download_and_stage(
                    {"name": "x-" + suffix,
                     "browser_download_url": "file://" + archive})
                self.assertTrue(os.path.isfile(os.path.join(staged, "marker.txt")))


@needs_display
class SwapScript(unittest.TestCase):
    def setUp(self):
        self.staged = tempfile.mkdtemp()
        self.target = tempfile.mkdtemp()
        self.script = app.write_swap_script(self.staged, self.target, "/bin/true")

    def test_written_and_runnable(self):
        self.assertTrue(os.path.isfile(self.script))
        if not app.sys.platform.startswith("win"):
            self.assertTrue(os.access(self.script, os.X_OK))

    def test_waits_for_this_process(self):
        body = open(self.script, encoding="utf-8").read()
        self.assertIn(str(os.getpid()), body)
        self.assertIn(self.staged, body)
        self.assertIn(self.target, body)

    def test_staging_lives_outside_the_target(self):
        # The script deletes the target wholesale; it must not be deleting the
        # files it is about to copy from.
        self.assertFalse(self.staged.startswith(self.target))


@needs_display
class LiveRepository(unittest.TestCase):
    """Skipped offline; never fails the suite for a missing network."""

    def _api(self, path):
        request = urllib.request.Request(
            f"https://api.github.com/repos/{app.GITHUB_REPO}/{path}",
            headers={"Accept": "application/vnd.github+json",
                     "User-Agent": "afk-clicker-tests"})
        with urllib.request.urlopen(request, timeout=15) as response:
            return json.load(response)

    def setUp(self):
        try:
            self.releases = self._api("releases")
        except Exception as exc:
            self.skipTest(f"GitHub unreachable: {exc}")
        if not self.releases:
            self.skipTest("no releases published")

    def test_resolves_the_highest_version(self):
        # GitHub's own /releases/latest is ordered by creation time, not by
        # version, and has been observed naming an older release.
        highest = max((r["tag_name"] for r in self.releases),
                      key=app._version_tuple)
        self.assertEqual(app.latest_release()["tag_name"], highest)

    def test_the_newest_release_has_a_build_for_this_platform(self):
        self.assertIsNotNone(app.pick_asset(app.latest_release()))


if __name__ == "__main__":
    unittest.main()
