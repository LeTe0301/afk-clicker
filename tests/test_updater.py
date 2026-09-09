"""Version resolution, asset selection, staging and the swap script."""
import json
import os
import tarfile
import tempfile
import pathlib
import unittest
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

    def test_picks_the_asset_matching_this_platform(self):
        expected = {"win32": "w", "darwin": "m"}.get(app.sys.platform, "l")
        picked = app.pick_asset(self.RELEASE)
        self.assertIsNotNone(picked)
        # Assert *which* one. Merely asserting "not None" passed even with the
        # selection hard-coded to the wrong platform.
        self.assertEqual(picked["browser_download_url"], expected)

    def test_a_release_without_our_platform_yields_none(self):
        others = {"win32": "linux-x86_64.tar.gz"}.get(app.sys.platform, "windows-x64.zip")
        self.assertIsNone(app.pick_asset(
            {"assets": [{"name": "AFK-Farm-Clicker-" + others,
                         "browser_download_url": "x"}]}))

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
                    # as_uri(), not "file://" + path: a Windows drive path is
                    # not a valid file URL.
                    {"name": "x-" + suffix,
                     "browser_download_url": pathlib.Path(archive).as_uri()})
                marker = os.path.join(staged, "marker.txt")
                self.assertTrue(os.path.isfile(marker))
                # Check the content, not merely that a file exists -- the old
                # assertion passed for an empty extraction of the wrong tree.
                with open(marker, encoding="utf-8") as fh:
                    self.assertEqual(fh.read(), "hello")
                self.assertFalse(os.path.isdir(os.path.join(staged, "AFK Farm Clicker")),
                                 "the top-level folder should have been flattened away")


@needs_display
class SwapScript(unittest.TestCase):
    def setUp(self):
        # Mirror what download_and_stage produces: <workdir>/staged/<tree>.
        # A one-level-deep path made write_swap_script walk up to "/" and the
        # test wrote apply-update.sh into the filesystem root.
        workdir = tempfile.mkdtemp()
        self.staged = os.path.join(workdir, "staged", "AFK Farm Clicker")
        os.makedirs(self.staged)
        self.target = tempfile.mkdtemp()
        self.script = app.write_swap_script(self.staged, self.target, "/bin/true")

    def test_written_inside_the_working_directory_not_the_root(self):
        parent = os.path.dirname(os.path.abspath(self.script))
        self.assertNotEqual(parent, os.path.dirname(parent),
                            "the swap script must never land in the filesystem root")

    def test_a_shallow_staging_path_does_not_walk_up_to_the_root(self):
        # The case the guard exists for, and the one the deepened fixture above
        # no longer reaches. write_swap_script goes two directories up from
        # `staged`; when that lands on the filesystem root the script was
        # written into it.
        #
        # The path is constructed rather than taken from mkdtemp: a temp
        # directory is two levels deep on Linux ("/tmp/x") but far deeper on
        # Windows ("C:\\Users\\RUNNER~1\\AppData\\Local\\Temp\\x") and macOS
        # ("/var/folders/.../x"), so the previous version asserted a Linux-only
        # precondition and failed outright on the other two. It never touches
        # the disk -- write_swap_script only reads it as a string.
        root = os.path.abspath(os.sep)
        shallow = os.path.join(root, "staged", "AFK Farm Clicker")
        two_up = os.path.dirname(os.path.dirname(shallow))
        self.assertEqual(two_up, root, "constructed path must sit two below the root")

        script = app.write_swap_script(shallow, self.target, "/bin/true")
        parent = os.path.dirname(os.path.abspath(script))
        self.assertNotEqual(parent, root,
                            f"swap script landed in the filesystem root: {script}")
        self.assertTrue(os.access(parent, os.W_OK))

    def test_written_and_runnable(self):
        self.assertTrue(os.path.isfile(self.script))
        if not app.sys.platform.startswith("win"):
            self.assertTrue(os.access(self.script, os.X_OK))

    def test_waits_for_this_process_rather_than_killing_it(self):
        body = open(self.script, encoding="utf-8").read()
        self.assertIn(str(os.getpid()), body)
        self.assertIn(self.staged, body)
        self.assertIn(self.target, body)
        # Naming the pid is not enough: the script must *poll* for the process
        # to exit. Signalling it would kill the very program being updated.
        if app.sys.platform == "win32":
            self.assertIn("tasklist", body)
        else:
            self.assertIn("kill -0", body)
        for lethal in ("kill -9", "kill -15", "kill -TERM", "taskkill"):
            self.assertNotIn(lethal, body)

    def test_the_script_never_deletes_what_it_copies_from(self):
        # Comparing two independently created temp directories was tautological
        # -- they could never overlap, so the assertion held no matter what
        # write_swap_script did. What matters is the relationship the *script*
        # sets up between the two paths it was handed.
        body = open(self.script, encoding="utf-8").read()
        staged, target = os.path.abspath(self.staged), os.path.abspath(self.target)
        self.assertFalse(
            os.path.commonpath([staged, target]) in (staged, target),
            "the staging tree and the target must not contain one another")
        # And the destructive step must be aimed at the target.
        #
        # "staged must not appear on a destructive line" was the wrong rule:
        # robocopy /MIR is the copy *and* the prune in one command, so the
        # source legitimately appears on it. What matters is the direction --
        # /MIR mirrors the first argument onto the second and only ever deletes
        # in the second.
        for line in body.splitlines():
            stripped = line.strip()
            if "/MIR" in stripped:
                self.assertLess(stripped.index(staged), stripped.index(target),
                                f"robocopy would mirror the target onto the staging tree: {stripped}")
            elif "-delete" in stripped or stripped.startswith("rm -rf"):
                self.assertIn(target, stripped)
                self.assertNotIn(staged, stripped,
                                 f"destructive step touches the staging tree: {stripped}")

    def test_the_script_copies_and_relaunches(self):
        # The wait loop was asserted; the two steps that make it an update
        # rather than a deletion were not.
        body = open(self.script, encoding="utf-8").read()
        self.assertIn(self.staged, body)
        self.assertIn(self.target, body)
        if app.sys.platform == "win32":
            self.assertIn("robocopy", body)
            self.assertIn("start", body)
        else:
            self.assertIn("cp -a", body)
        self.assertIn("/bin/true", body, "the new build is never started")


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
        self.releases = [r for r in self.releases
                         if not r.get("draft") and not r.get("prerelease")]
        if not self.releases:
            # A repository with nothing but prereleases is a legitimate state,
            # not a broken updater.
            self.skipTest("no published non-prerelease releases")

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
