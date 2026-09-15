"""Version resolution, asset selection, staging and the swap script."""
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import hashlib
import pathlib
import unittest
import urllib.parse
import urllib.request
import zipfile

from .context import app, needs_display

# tests/context.py puts this on sys.path for the in-process suite; the
# Windows launch reproduction below needs it again inside a *separate*
# interpreter (see WindowsLaunchReproduction._LAUNCHER), which does not
# inherit that path-insert.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


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
class SafeVersionTag(unittest.TestCase):
    """_is_safe_version_tag() -- the gate _install_worker puts between an
    untrusted GitHub API tag_name and write_swap_script's target_version
    (PR #72 security review: a crafted tag_name was proven live to run
    arbitrary shell commands through the generated update script)."""

    def test_accepts_this_project_s_own_tag_shape(self):
        for tag in ("v0.7.0", "v1.0.0", "v0.10.0", "0.7.0"):
            with self.subTest(tag=tag):
                self.assertTrue(app._is_safe_version_tag(tag))

    def test_rejects_shell_metacharacters(self):
        dangerous = [
            "$(touch /tmp/x)", "v1.0.0`touch /tmp/x`",
            'v1.0.0"; touch /tmp/x; "', "v1.0.0 && touch /tmp/x",
            "v1.0.0 | touch /tmp/x", "v1.0.0; rm -rf /", "v1.0.0\ntouch /tmp/x",
        ]
        for tag in dangerous:
            with self.subTest(tag=tag):
                self.assertFalse(app._is_safe_version_tag(tag))

    def test_rejects_an_oversized_tag(self):
        self.assertFalse(app._is_safe_version_tag("v" + "9" * 40 + ".0.0"))

    def test_rejects_the_wrong_number_of_parts(self):
        for tag in ("v1.0", "v1.0.0.0", "v1"):
            with self.subTest(tag=tag):
                self.assertFalse(app._is_safe_version_tag(tag))

    def test_rejects_non_digit_parts(self):
        for tag in ("v1.0.x", "vx.y.z", "v1.0.0-rc1", " v1.0.0"):
            with self.subTest(tag=tag):
                self.assertFalse(app._is_safe_version_tag(tag))

    def test_rejects_non_string_and_empty(self):
        for tag in (None, 123, "", [], {}):
            with self.subTest(tag=tag):
                self.assertFalse(app._is_safe_version_tag(tag))


@needs_display
class AssetSelection(unittest.TestCase):
    RELEASE = {"assets": [
        {"name": "Clickwork-windows-x64.zip", "browser_download_url": "w"},
        {"name": "Clickwork-linux-x86_64.tar.gz", "browser_download_url": "l"},
        {"name": "Clickwork-macos-arm64.zip", "browser_download_url": "m"},
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
            {"assets": [{"name": "Clickwork-" + others,
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
                name = "x-" + suffix
                staged = app.download_and_stage(
                    # as_uri(), not "file://" + path: a Windows drive path is
                    # not a valid file URL.
                    {"name": name, "browser_download_url": pathlib.Path(archive).as_uri()},
                    checksums={name: app.file_digest(archive)})
                marker = os.path.join(staged, "marker.txt")
                self.assertTrue(os.path.isfile(marker))
                # Check the content, not merely that a file exists -- the old
                # assertion passed for an empty extraction of the wrong tree.
                with open(marker, encoding="utf-8") as fh:
                    self.assertEqual(fh.read(), "hello")
                self.assertFalse(os.path.isdir(os.path.join(staged, "AFK Farm Clicker")),
                                 "the top-level folder should have been flattened away")


@needs_display
class Checksums(unittest.TestCase):
    """The updater downloads code and then runs it. It must check what it got."""

    def _release(self, names):
        return {"assets": [{"name": n, "browser_download_url": "x"} for n in names]}

    def test_picks_the_checksum_asset(self):
        rel = self._release(["Clickwork-windows-x64.zip", "SHA256SUMS"])
        self.assertEqual(app.pick_checksums(rel)["name"], "SHA256SUMS")

    def test_a_release_without_checksums(self):
        self.assertIsNone(app.pick_checksums(self._release(["something.zip"])))
        self.assertIsNone(app.pick_checksums({}))
        self.assertIsNone(app.pick_checksums(None))

    def test_parses_sha256sum_output(self):
        digest = "a" * 64
        blob = (f"{digest}  plain.zip\n"
                f"{digest.upper()}  *binary-mode.tar.gz\n"
                "not a checksum line\n"
                f"{'b' * 63}  too-short.zip\n")
        path = os.path.join(tempfile.mkdtemp(), "SHA256SUMS")
        open(path, "w").write(blob)
        sums = app.fetch_checksums(
            {"browser_download_url": pathlib.Path(path).as_uri()})
        # The leading "*" marks binary mode and is not part of the name; the
        # digest is normalised to lower case so comparison cannot miss.
        self.assertEqual(sums, {"plain.zip": digest, "binary-mode.tar.gz": digest})

    def test_file_digest_matches_hashlib(self):
        path = os.path.join(tempfile.mkdtemp(), "payload.bin")
        data = os.urandom(3 * 1024 * 1024 + 7)      # spans several read chunks
        open(path, "wb").write(data)
        self.assertEqual(app.file_digest(path), hashlib.sha256(data).hexdigest())


@needs_display
class StagingSafety(unittest.TestCase):
    """Verification happens before extraction, and extraction cannot escape."""

    def _zip(self, entries):
        base = tempfile.mkdtemp()
        path = os.path.join(base, "pkg-windows-x64.zip")
        with zipfile.ZipFile(path, "w") as zf:
            for name, body in entries.items():
                zf.writestr(name, body)
        return path

    def _asset(self, path):
        return {"name": os.path.basename(path),
                "browser_download_url": pathlib.Path(path).as_uri()}

    def test_a_matching_digest_is_accepted(self):
        path = self._zip({"AFK Farm Clicker/marker.txt": "hello"})
        asset = self._asset(path)
        staged = app.download_and_stage(
            asset, checksums={asset["name"]: app.file_digest(path)})
        self.assertTrue(os.path.isfile(os.path.join(staged, "marker.txt")))

    def test_a_wrong_digest_is_refused(self):
        path = self._zip({"AFK Farm Clicker/marker.txt": "hello"})
        asset = self._asset(path)
        with self.assertRaises(app.ChecksumError) as caught:
            app.download_and_stage(asset, checksums={asset["name"]: "c" * 64})
        self.assertIn("mismatch", str(caught.exception))

    def test_the_mismatch_message_survives_status_line_truncation(self):
        # Same 40-char budget as the unlisted case, exercised with a
        # realistic release asset name to confirm the fixed "checksum
        # mismatch" prefix (which does not embed the asset name at all)
        # already keeps the category intact -- unlike the unlisted-archive
        # message before its fix.
        base = tempfile.mkdtemp()
        real_path = os.path.join(base, "Clickwork-macos-arm64.zip")
        with zipfile.ZipFile(real_path, "w") as zf:
            zf.writestr("AFK Farm Clicker/marker.txt", "hello")
        asset = self._asset(real_path)
        with self.assertRaises(app.ChecksumError) as caught:
            app.download_and_stage(asset, checksums={asset["name"]: "d" * 64})
        shown = str(caught.exception)[:40].lower()
        self.assertIn("mismatch", shown, f"status line {shown!r} does not read as a checksum failure")

    def test_an_unlisted_archive_is_refused(self):
        path = self._zip({"AFK Farm Clicker/marker.txt": "hello"})
        with self.assertRaises(app.ChecksumError):
            app.download_and_stage(self._asset(path), checksums={"other.zip": "d" * 64})

    def test_the_unlisted_message_survives_status_line_truncation(self):
        # _install_worker shows str(exc)[:40] (afk_clicker.py:2069), and a real
        # release asset is named like the release workflow does it --
        # "Clickwork-windows-x64.zip", not "pkg-windows-x64.zip". At that
        # length the reason is pushed past character 40 and the user sees only
        # "<name> is not ", with no word telling them it is a checksum problem.
        base = tempfile.mkdtemp()
        real_path = os.path.join(base, "Clickwork-windows-x64.zip")
        with zipfile.ZipFile(real_path, "w") as zf:
            zf.writestr("AFK Farm Clicker/marker.txt", "hello")
        asset = self._asset(real_path)
        with self.assertRaises(app.ChecksumError) as caught:
            app.download_and_stage(asset, checksums={"other.zip": "d" * 64})
        shown = str(caught.exception)[:40].lower()
        self.assertTrue("checksum" in shown or "sha256sums" in shown,
                         f"status line {shown!r} does not read as a checksum failure")

    def test_nothing_is_extracted_when_the_digest_is_wrong(self):
        # Verification must come first: extraction is the step that puts
        # attacker-controlled names onto the filesystem.
        path = self._zip({"AFK Farm Clicker/marker.txt": "hello"})
        asset = self._asset(path)
        before = set(os.listdir(os.path.dirname(path)))
        with self.assertRaises(app.ChecksumError):
            app.download_and_stage(asset, checksums={asset["name"]: "e" * 64})
        marker = os.path.join(os.path.dirname(path), "staged")
        self.assertFalse(os.path.exists(marker))
        self.assertEqual(set(os.listdir(os.path.dirname(path))) - before, set())

    def test_checksums_none_extracts_nothing(self):
        # checksums is a required argument (afk_clicker.py:download_and_stage);
        # an explicit None is a caller bug, not a request to skip
        # verification. Whatever exception that raises, extraction must not
        # have happened -- the same guarantee as a wrong digest.
        path = self._zip({"AFK Farm Clicker/marker.txt": "hello"})
        asset = self._asset(path)
        before = set(os.listdir(os.path.dirname(path)))
        with self.assertRaises(Exception):
            app.download_and_stage(asset, checksums=None)
        marker = os.path.join(os.path.dirname(path), "staged")
        self.assertFalse(os.path.exists(marker))
        self.assertEqual(set(os.listdir(os.path.dirname(path))) - before, set())

    def test_an_entry_escaping_the_directory_is_refused(self):
        # zipfile writes the member name as given; "../.." lands outside.
        path = self._zip({"../../escaped.txt": "gotcha"})
        asset = self._asset(path)
        with self.assertRaises(app.ChecksumError) as caught:
            app.download_and_stage(asset, checksums={asset["name"]: app.file_digest(path)})
        self.assertIn("escapes", str(caught.exception))

    def test_the_escape_message_survives_status_line_truncation(self):
        # The archive entry name -- not the asset name -- is the
        # attacker-controlled variable-length part here. A long enough entry
        # name must not push "escapes" past the 40-character budget either.
        long_name = "../../" + "nested-directory-component/" * 4 + "escaped.txt"
        path = self._zip({long_name: "gotcha"})
        asset = self._asset(path)
        with self.assertRaises(app.ChecksumError) as caught:
            app.download_and_stage(asset, checksums={asset["name"]: app.file_digest(path)})
        shown = str(caught.exception)[:40].lower()
        self.assertIn("escapes", shown, f"status line {shown!r} does not read as an unsafe-entry failure")

    def test_an_absolute_entry_is_refused(self):
        path = self._zip({"/tmp/afk-clicker-escape.txt": "gotcha"})
        asset = self._asset(path)
        with self.assertRaises(app.ChecksumError):
            app.download_and_stage(asset, checksums={asset["name"]: app.file_digest(path)})

    def _tar_with(self, extra):
        base = tempfile.mkdtemp()
        payload = os.path.join(base, "tree")
        os.makedirs(payload)
        with open(os.path.join(payload, "marker.txt"), "w") as fh:
            fh.write("hello")
        extra(payload)
        path = os.path.join(base, "pkg-linux-x86_64.tar.gz")
        with tarfile.open(path, "w:gz") as tf:
            tf.add(payload, arcname="AFK Farm Clicker")
        return path

    def _tar_with_entry_type(self, name, entry_type):
        """
        Like _tar_with, but for entry kinds that cannot be created as real
        files cross-platform -- os.mkfifo does not exist on Windows, and
        device nodes need root everywhere. These tests check tarfile's own
        type byte, not any filesystem behaviour, so the archive entry is
        built directly with a TarInfo and addfile() instead of created on
        disk and then tarred up.
        """
        base = tempfile.mkdtemp()
        payload = os.path.join(base, "tree")
        os.makedirs(payload)
        with open(os.path.join(payload, "marker.txt"), "w") as fh:
            fh.write("hello")
        path = os.path.join(base, "pkg-linux-x86_64.tar.gz")
        with tarfile.open(path, "w:gz") as tf:
            tf.add(payload, arcname="AFK Farm Clicker")
            info = tarfile.TarInfo(name=f"AFK Farm Clicker/{name}")
            info.type = entry_type
            tf.addfile(info)
        return path

    def test_a_plain_tar_is_accepted(self):
        path = self._tar_with(lambda d: None)
        asset = self._asset(path)
        staged = app.download_and_stage(
            asset, checksums={asset["name"]: app.file_digest(path)})
        self.assertTrue(os.path.isfile(os.path.join(staged, "marker.txt")))

    def test_a_tar_symlink_is_refused(self):
        # The reason this is checked explicitly rather than left to
        # extractall(filter="data"): that argument does not exist before
        # Python 3.12, and the fallback path wrote the symlink to disk.
        path = self._tar_with(
            lambda d: os.symlink("/etc/passwd", os.path.join(d, "link")))
        asset = self._asset(path)
        with self.assertRaises(app.ChecksumError) as caught:
            app.download_and_stage(asset, checksums={asset["name"]: app.file_digest(path)})
        self.assertIn("link entry", str(caught.exception))

    def test_the_link_message_survives_status_line_truncation(self):
        long_name = "deeply-nested-symlink-name-" * 3
        path = self._tar_with(
            lambda d: os.symlink("/etc/passwd", os.path.join(d, long_name)))
        asset = self._asset(path)
        with self.assertRaises(app.ChecksumError) as caught:
            app.download_and_stage(asset, checksums={asset["name"]: app.file_digest(path)})
        shown = str(caught.exception)[:40].lower()
        self.assertIn("link entry", shown, f"status line {shown!r} does not read as an unsafe-entry failure")

    def test_a_tar_hardlink_is_refused(self):
        def add_hardlink(d):
            os.link(os.path.join(d, "marker.txt"), os.path.join(d, "hard"))
        path = self._tar_with(add_hardlink)
        asset = self._asset(path)
        with self.assertRaises(app.ChecksumError):
            app.download_and_stage(asset, checksums={asset["name"]: app.file_digest(path)})

    def test_a_tar_fifo_is_refused(self):
        path = self._tar_with_entry_type("pipe", tarfile.FIFOTYPE)
        asset = self._asset(path)
        with self.assertRaises(app.ChecksumError) as caught:
            app.download_and_stage(asset, checksums={asset["name"]: app.file_digest(path)})
        self.assertIn("device entry", str(caught.exception))

    def test_the_device_message_survives_status_line_truncation(self):
        long_name = "deeply-nested-fifo-name-" * 3
        path = self._tar_with_entry_type(long_name, tarfile.FIFOTYPE)
        asset = self._asset(path)
        with self.assertRaises(app.ChecksumError) as caught:
            app.download_and_stage(asset, checksums={asset["name"]: app.file_digest(path)})
        shown = str(caught.exception)[:40].lower()
        self.assertIn("device entry", shown, f"status line {shown!r} does not read as an unsafe-entry failure")


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
        self.log_path = os.path.join(workdir, "update.log")
        self.script = app.write_swap_script(self.staged, self.target, "/bin/true", self.log_path)

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

        log_path = os.path.join(tempfile.mkdtemp(), "update.log")
        script = app.write_swap_script(shallow, self.target, "/bin/true", log_path)
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
        # And it must clear the old installation first. Without this line the
        # update is a copy-over: every file dropped between releases survives
        # forever, and nothing else in the suite notices.
        if app.sys.platform == "win32":
            self.assertIn("/MIR", body, "robocopy would not prune the old build")
        else:
            self.assertIn("-mindepth 1 -delete", body,
                          "the old installation is never cleared")


@needs_display
class SwapScriptWindowsCmdText(unittest.TestCase):
    """
    Static checks on the *text* of the generated apply-update.cmd, run on
    whatever platform the suite executes on -- the Windows-only classes
    below (WindowsLaunchReproduction/WindowsFixSuspectDiagnostics) can
    actually run the .cmd for real, but only on windows-latest CI; this
    class checks what the .cmd contains everywhere, the same way SwapScript
    above already checks the .sh text on every platform.

    Monkeypatches app.sys.platform and restores it in a cleanup, the same
    style already used by tests/test_hotkey.py's InputPermission -- this
    suite deliberately avoids unittest.mock (see tests/test_ui.py:2119-2120).
    """

    def setUp(self):
        original_platform = app.sys.platform
        app.sys.platform = "win32"
        self.addCleanup(setattr, app.sys, "platform", original_platform)

        workdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, workdir, ignore_errors=True)
        self.staged = os.path.join(workdir, "staged", "AFK Farm Clicker")
        os.makedirs(self.staged)
        self.target = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.target, ignore_errors=True)
        # A settings directory that does not exist yet -- write_swap_script
        # must create it, the same as it will need to on a machine that has
        # never shipped an update log before.
        self.log_path = os.path.join(workdir, "settings", "update.log")
        self.script = app.write_swap_script(self.staged, self.target,
                                            "relaunch.exe", self.log_path)
        with open(self.script, encoding="utf-8") as fh:
            self.body = fh.read()

    def test_written_as_a_cmd_file(self):
        self.assertTrue(self.script.endswith(".cmd"), self.script)

    def test_the_log_directory_is_created(self):
        self.assertTrue(os.path.isdir(os.path.dirname(self.log_path)),
                        "write_swap_script must create the log's directory")

    def test_the_log_path_is_quoted(self):
        # A settings path can contain spaces (a Windows username with a
        # space is common -- "C:\\Users\\First Last\\AppData\\..."); `set
        # "LOG=value"` is the form that survives that, `set LOG=value` is not.
        self.assertIn(f'set "LOG={self.log_path}"', self.body)

    def test_no_timeout_left_in_the_wait_loop(self):
        # `timeout /t 1 /nobreak` refuses redirected stdin and exits at once
        # with no real console to read from, turning the wait loop into a
        # busy-loop of tasklist calls -- see write_swap_script's own comment.
        self.assertNotIn("timeout", self.body.lower())
        self.assertIn("ping -n 2 127.0.0.1", self.body,
                      "the console-free ~1s delay must replace timeout")

    def test_done_is_written_after_the_copy_exit_code(self):
        copy_index = self.body.index("copy exit code")
        done_index = self.body.index("done", copy_index)
        self.assertGreater(done_index, copy_index,
                          "done must be logged after the copy step, not before it")

    def test_every_log_line_carries_a_timestamp(self):
        # docs/spec.md's "Shipped update log": "a timestamp and a step
        # name" per line. %DATE% %TIME% is ordinary parse-time expansion
        # (not delayed expansion -- see write_swap_script's own comment),
        # so every "echo ... >> %LOG%"/"> %LOG% echo ..." line must carry it.
        log_lines = [line for line in self.body.splitlines()
                    if "echo" in line and '"%LOG%"' in line]
        self.assertTrue(log_lines, "no log-writing lines found in the script")
        for line in log_lines:
            self.assertIn("%DATE% %TIME%", line, f"missing timestamp: {line!r}")

    def test_relaunch_is_attempted_even_if_the_copy_fails(self):
        # start "" "{relaunch}" must not sit inside the same conditional that
        # guards the done line -- a failed mirror should still relaunch the
        # old build rather than leave the user with nothing (see
        # docs/implementation.md's "relaunch on failure" decision).
        relaunch_index = self.body.index('start "" "relaunch.exe"')
        done_guard_index = self.body.index("if %RC% LSS 8")
        self.assertLess(relaunch_index, done_guard_index,
                        "relaunch must not be gated behind the copy succeeding")

    def test_no_version_suffix_when_target_version_omitted(self):
        # G#36/GH#64: the 5 existing call sites (this class's own setUp
        # included) never pass target_version, so the start line must stay
        # byte-identical to the pre-feature text -- no "version=" anywhere.
        self.assertNotIn("version=", self.body)

    def test_version_suffix_when_target_version_given(self):
        log_path = os.path.join(tempfile.mkdtemp(), "update.log")
        script = app.write_swap_script(self.staged, self.target, "relaunch.exe",
                                       log_path, target_version="v0.7.0")
        with open(script, encoding="utf-8") as fh:
            body = fh.read()
        start_line = next(line for line in body.splitlines() if "start pid=" in line)
        self.assertIn('version="v0.7.0"', start_line)


@unittest.skipIf(sys.platform == "win32",
                 "runs the .sh path via /bin/sh directly; the .cmd path is "
                 "covered on Windows by SwapScriptWindowsCmdText (text) and "
                 "the Windows-only classes below (execution, on CI)")
@needs_display
class SwapScriptLogLifecycle(unittest.TestCase):
    """
    Local (Linux/macOS), end-to-end exercise of the shipped update log
    (docs/spec.md Goals, "Shipped update log") by actually running the
    generated apply-update.sh against real temp directories.

    write_swap_script always waits on os.getpid() of whichever process
    calls it. Calling it directly from this test method would make the
    generated script wait on the test runner's own still-alive pid and hang
    until the subprocess timeout below. So, the same way the Windows launch
    reproduction spawns a short-lived process to get a real pid that then
    exits on its own, write_swap_script is called here from a short-lived
    `python -c` subprocess -- by the time this test runs the script, that
    pid has already exited and the wait loop ends at once.

    @needs_display is not about Tk here (this class never builds one) --
    it's needed because the subprocess above does `import afk_clicker`,
    which imports pynput unconditionally at module level, which raises
    without an X display on Linux. skipIf(win32) above is the actual
    platform guard for this class: HEADLESS (needs_display's condition) is
    hard-coded to Linux-only, so without it this class would still be
    collected and run on windows-latest CI -- and immediately error, since
    Windows has no /bin/sh to invoke.
    """

    def _write_script_in_subprocess(self, staged, target, relaunch, log_path,
                                    target_version=None):
        code = ("import sys; sys.path.insert(0, sys.argv[1]); "
               "import afk_clicker as app; "
               "print(app.write_swap_script(sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5], "
               "target_version=(sys.argv[6] if len(sys.argv) > 6 else None)))")
        args = [sys.executable, "-c", code, ROOT, staged, target, relaunch, log_path]
        if target_version is not None:
            args.append(target_version)
        result = subprocess.run(args, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip()

    def _run(self, script):
        return subprocess.run(["/bin/sh", script], capture_output=True,
                              text=True, timeout=10)

    def _fixture(self, workdir, stage_missing=False):
        staged = os.path.join(workdir, "staged")
        if not stage_missing:
            os.makedirs(staged)
            with open(os.path.join(staged, "new.txt"), "w", encoding="utf-8") as fh:
                fh.write("new")
        target = os.path.join(workdir, "target")
        os.makedirs(target)
        with open(os.path.join(target, "old.txt"), "w", encoding="utf-8") as fh:
            fh.write("old")
        relaunch = os.path.join(workdir, "relaunch.sh")
        marker = os.path.join(workdir, "relaunched.marker")
        with open(relaunch, "w", encoding="utf-8") as fh:
            fh.write(f'#!/bin/sh\necho relaunched > "{marker}"\n')
        os.chmod(relaunch, 0o755)
        return staged, target, relaunch, marker

    def test_successful_update_ends_with_done_and_records_the_exit_code(self):
        workdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, workdir, ignore_errors=True)
        staged, target, relaunch, marker = self._fixture(workdir)
        log_path = os.path.join(workdir, "update.log")

        script = self._write_script_in_subprocess(staged, target, relaunch, log_path)
        result = self._run(script)
        self.assertEqual(result.returncode, 0, result.stderr)

        self.assertTrue(os.path.isfile(os.path.join(target, "new.txt")))
        self.assertFalse(os.path.exists(os.path.join(target, "old.txt")))
        self.assertTrue(os.path.exists(marker), "the relaunch step never ran")

        log = open(log_path, encoding="utf-8").read()
        self.assertIn("copy exit code 0", log)
        lines = [line for line in log.splitlines() if line.strip()]
        self.assertTrue(lines[-1].strip().endswith("done"), log)

    def test_every_line_is_timestamped(self):
        # docs/spec.md's "Shipped update log": "a timestamp and a step
        # name" per line -- sabotage-verified in docs/implementation.md's
        # Round 3 section by stripping the prefix from one line and
        # confirming this goes red.
        workdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, workdir, ignore_errors=True)
        staged, target, relaunch, marker = self._fixture(workdir)
        log_path = os.path.join(workdir, "update.log")

        script = self._write_script_in_subprocess(staged, target, relaunch, log_path)
        self._run(script)

        log = open(log_path, encoding="utf-8").read()
        lines = [line for line in log.splitlines() if line.strip()]
        self.assertTrue(lines, "the log is empty")
        timestamp = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} ")
        for line in lines:
            self.assertRegex(line, timestamp,
                            f"line missing a YYYY-MM-DD HH:MM:SS prefix: {line!r}")

    def test_a_failing_copy_records_a_nonzero_exit_code_and_never_writes_done(self):
        workdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, workdir, ignore_errors=True)
        # staged is deliberately never created, so `cp -a "{staged}/." ...`
        # fails with a nonzero exit code.
        staged, target, relaunch, marker = self._fixture(workdir, stage_missing=True)
        log_path = os.path.join(workdir, "update.log")

        script = self._write_script_in_subprocess(staged, target, relaunch, log_path)
        self._run(script)

        log = open(log_path, encoding="utf-8").read()
        self.assertIn("copy exit code", log)
        self.assertNotIn("copy exit code 0", log)
        self.assertFalse(log.strip().endswith("done"), log)

    def test_target_version_recorded_on_the_start_line_when_given(self):
        # G#36/GH#64: the sh variant of the same target_version suffix
        # SwapScriptWindowsCmdText already checks on the .cmd text.
        workdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, workdir, ignore_errors=True)
        staged, target, relaunch, marker = self._fixture(workdir)
        log_path = os.path.join(workdir, "update.log")

        script = self._write_script_in_subprocess(staged, target, relaunch, log_path,
                                                   target_version="v0.7.0")
        self._run(script)

        log = open(log_path, encoding="utf-8").read()
        start_line = next(line for line in log.splitlines() if "start pid=" in line)
        self.assertIn('version="v0.7.0"', start_line)

    def test_no_version_field_when_target_version_omitted(self):
        workdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, workdir, ignore_errors=True)
        staged, target, relaunch, marker = self._fixture(workdir)
        log_path = os.path.join(workdir, "update.log")

        script = self._write_script_in_subprocess(staged, target, relaunch, log_path)
        self._run(script)

        log = open(log_path, encoding="utf-8").read()
        self.assertNotIn("version=", log)

    def test_a_second_update_truncates_the_log_rather_than_appending(self):
        workdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, workdir, ignore_errors=True)
        staged, target, relaunch, marker = self._fixture(workdir)
        log_path = os.path.join(workdir, "update.log")

        script = self._write_script_in_subprocess(staged, target, relaunch, log_path)
        self._run(script)
        first_run_lines = open(log_path, encoding="utf-8").read().splitlines()

        script = self._write_script_in_subprocess(staged, target, relaunch, log_path)
        self._run(script)
        second_run_lines = open(log_path, encoding="utf-8").read().splitlines()

        self.assertEqual(len(second_run_lines), len(first_run_lines),
                        "the log grew between runs -- looks appended, not truncated")
        start_lines = [line for line in second_run_lines if "start pid=" in line]
        self.assertEqual(len(start_lines), 1, second_run_lines)


class _SwapScriptLauncher:
    """
    Shared fixture/launch machinery for the two Windows-only test classes
    below. Deliberately *not* a unittest.TestCase subclass: both
    WindowsLaunchReproduction and WindowsFixSuspectDiagnostics need this
    setup, but unittest discovers every test_* method on every TestCase
    subclass, so inheriting one from the other would silently re-run the
    acceptance case as part of the "never fails the suite" diagnostics class.

    G#35/GH#63: `_quit_for_update`'s Windows branch (afk_clicker.py:2979-2986)
    launches `apply-update.cmd` and the app then exits right away -- and on a
    real machine the swap script never finishes. `SwapScript` above only
    checks what write_swap_script *writes*; nothing exercised how
    `_quit_for_update` actually *launches* it, which is exactly the gap that
    let this ship.

    Reproducing suspect 3 (the process tree not surviving its parent exiting)
    requires the *caller* of write_swap_script to actually be a separate OS
    process that exits -- calling write_swap_script in-process would make
    os.getpid() the test runner's own pid, and the test runner does not exit
    after Popen() returns. So this spawns a short-lived "launcher" subprocess
    (a `python -c` script) that stands in for on_close(): it calls the real
    write_swap_script, launches the result exactly as _quit_for_update does,
    then exits immediately.
    """

    # OLD_CREATIONFLAGS is what shipped before this fix (afk_clicker.py's
    # old _quit_for_update, pre G#35/GH#63) -- kept only for
    # WindowsFixSuspectDiagnostics, which deliberately re-runs the *old*
    # broken flags through the *new* logging script to show, from the log
    # itself, exactly which step stalls. The acceptance case below no
    # longer hand-copies any flags at all: it calls app.launch_swap_script,
    # so it can never drift from whatever creationflags production actually
    # uses.
    OLD_CREATIONFLAGS = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP

    # Runs in a fresh interpreter (a `python -c` subprocess), so it cannot
    # see this test module's locals -- everything it needs crosses the
    # process boundary as an environment variable instead of being
    # string-formatted into the source below, which would turn a staged path
    # containing a quote or backslash into a syntax error or, worse, an
    # injection. AFK_TEST_ERROR_LOG travels as its own env var rather than a
    # key inside the JSON cfg so that even a cfg parse failure still lands
    # somewhere readable.
    _LAUNCHER = """
import os, sys, traceback

error_log = os.environ["AFK_TEST_ERROR_LOG"]
try:
    import json, subprocess, time

    sys.path.insert(0, os.environ["AFK_TEST_ROOT"])
    import afk_clicker as app

    cfg = json.loads(os.environ["AFK_TEST_CFG"])
    script = app.write_swap_script(cfg["staged"], cfg["target"], cfg["relaunch"], cfg["log_path"])

    if cfg["stdio_mode"] == "production":
        # The acceptance case: the exact call _quit_for_update makes, so
        # this can never drift from what production actually runs.
        app.launch_swap_script(script)
    else:
        # WindowsFixSuspectDiagnostics only, below -- reproducing the old,
        # pre-fix launch shape to see where it stalled.
        kwargs = {"creationflags": cfg["creationflags"]}
        if cfg["stdio_mode"] == "devnull":
            kwargs["stdin"] = subprocess.DEVNULL
            kwargs["stdout"] = subprocess.DEVNULL
            kwargs["stderr"] = subprocess.DEVNULL
        # stdio_mode == "none": no stdio kwargs at all -- the exact old,
        # pre-fix line (no DEVNULL, no CREATE_NO_WINDOW).
        subprocess.Popen(["cmd", "/c", script], **kwargs)

    # Stands in for on_close() tearing the real app down right after Popen()
    # returns. A launcher that stayed alive for the rest of the test would
    # never put suspect 3 (the process tree dying with its parent) under
    # test at all.
    if cfg["keep_alive_seconds"]:
        time.sleep(cfg["keep_alive_seconds"])
except Exception:
    # No print(): this interpreter is often pythonw.exe (see
    # _gui_interpreter), chosen specifically because it -- like the frozen
    # --windowed app -- has no console and cannot be assumed to have a
    # working stdout/stderr to print to. A crash has to reach disk some
    # other way to be visible at all.
    with open(error_log, "w", encoding="utf-8") as fh:
        fh.write(traceback.format_exc())
"""

    def _gui_interpreter(self):
        # pythonw.exe -- GUI subsystem, no console -- sits next to python.exe
        # in a normal CPython install. The real app is a PyInstaller
        # `--windowed` build with the same no-console shape; python.exe
        # (a console-subsystem process) would hand cmd.exe a real inherited
        # console that production's launch never provides, which is exactly
        # what this reproduction cannot afford to get wrong. Falls back to
        # sys.executable for an install that does not ship pythonw.exe (e.g.
        # some embeddable distributions).
        candidate = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
        return candidate if os.path.isfile(candidate) else sys.executable

    def _kill_stragglers(self):
        # Best-effort cleanup, not an assertion: the acceptance case's whole
        # premise is that the process tree may *still be alive* past the
        # poll timeout (that is the bug). A straggling robocopy/cmd would
        # otherwise hold a lock on a temp dir past this test's own
        # shutil.rmtree cleanup and confuse whatever test runs next. Every
        # workdir either class creates shares the "afk-repro" prefix, so
        # matching on it (rather than on one specific workdir) catches both.
        #
        # Round 4: this also already covers a straggling relaunch.exe (the
        # copied python.exe stuck at an interactive prompt if PYTHONSTARTUP
        # somehow never ran) without needing its own image-name match --
        # `start "" "<full path>"` puts that full path, which always lives
        # under this test's own "afk-repro*" workdir, straight into the
        # resulting process's own CommandLine.
        try:
            subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "Get-CimInstance Win32_Process | "
                 "Where-Object { $_.CommandLine -like '*afk-repro*' } | "
                 "ForEach-Object { Stop-Process -Id $_.ProcessId -Force "
                 "-ErrorAction SilentlyContinue }"],
                timeout=15, capture_output=True, text=True)
        except Exception as exc:
            print(f"[tearDown] straggler cleanup failed (non-fatal): {exc}")

    def _fixture_in(self, workdir):
        """
        staged/target laid out the way download_and_stage and install_root
        hand them to write_swap_script in production. `target` sits under a
        directory with a space *and* a realistic set of cmd-meaningful
        characters -- "(", ")", "&", "^", "!" (the shape of "C:\\Program
        Files (x86)\\..." and "Tom & Jerry" -- Round 3, PR #65 review: CI so
        far only proved a plain space survives the existing quoting). `%` is
        deliberately left out: it already breaks the pre-existing
        robocopy/start lines (cmd expands `%...%` sequences inside the
        interpolated script text) -- a limitation that predates this fix,
        documented but not solved in docs/implementation.md.

        Round 4 (PR #65 review, round 3 CI): does *not* build `relaunch`
        any more -- see _build_relaunch_exe/_build_relaunch_cmd below.
        Round 3's CI run mirrored the target fine (`copy exit code 3`,
        robocopy's own "files copied + extras purged" code) but never wrote
        the relaunch marker, with two `cmd.exe` left over. Hypothesis: a
        `.cmd` needs `cmd.exe` to run it at all, and `start "" "<path>"`
        launching a `.cmd`/`.bat` does so via a *nested* `cmd /c`, whose own
        quote-stripping rule (strip the outer quotes when the string
        contains `&()^` between them) can break the path at the `&` --
        production's actual relaunch target is `sys.executable`, a real
        `.exe`, which `start` launches directly via CreateProcess with no
        nested shell to re-parse anything. Returns (staged, target, marker)
        -- callers build whichever relaunch target they need against the
        same marker path.
        """
        staged = os.path.join(workdir, "staged")
        os.makedirs(os.path.join(staged, "sub"))
        with open(os.path.join(staged, "new.txt"), "w", encoding="utf-8") as fh:
            fh.write("new")
        with open(os.path.join(staged, "sub", "nested.txt"), "w", encoding="utf-8") as fh:
            fh.write("nested")

        target = os.path.join(workdir, "target (x86) & co^!")
        os.makedirs(target)
        with open(os.path.join(target, "old.txt"), "w", encoding="utf-8") as fh:
            fh.write("old")

        marker = os.path.join(workdir, "relaunched.marker")
        return staged, target, marker

    def _build_relaunch_exe(self, workdir, dir_name="relaunch (x86) & co^!"):
        """
        A real, standalone .exe under a directory with the same
        cmd-meaningful characters as `target` by default -- standing in for
        production's actual relaunch target (`sys.executable`), which is
        always a real .exe, never a `.cmd`. `start` launches an .exe
        directly via CreateProcess; there is no nested cmd.exe to re-parse
        the path, which is exactly the axis Round 3's failure and the
        hypothesis above are about. dir_name is overridable so
        WindowsFixSuspectDiagnostics can run this exact same probe from a
        plain directory ("relaunch plain") -- isolating whether a failure
        is the probe mechanism itself or specifically the special
        characters (see that diagnostic's own docstring for the
        interpretation table).

        Built by copying the *running* interpreter's python.exe plus the
        DLLs it actually needs (globbed, not a fixed list -- the DLL name
        changes with the Python/VC-runtime version:
        `python3.dll`/`python3XY.dll`/`vcruntime140[_1].dll`) out of
        sys.base_prefix, rather than copying the whole install tree --
        smaller, and this test already has to clean up its own temp dir.
        The copy alone cannot find the standard library relative to its own
        (temp) location, so the caller must also set PYTHONHOME to the real
        sys.base_prefix in whatever environment it hands down the process
        tree (see WindowsLaunchReproduction's extra_env) -- PYTHONHOME
        overrides Python's normal "relative to the executable" prefix
        search, so the copy still finds Lib/DLLs at the real install even
        though the .exe file itself is a copy sitting somewhere else.
        """
        relaunch_dir = os.path.join(workdir, dir_name)
        os.makedirs(relaunch_dir, exist_ok=True)
        base = sys.base_prefix
        relaunch = os.path.join(relaunch_dir, "relaunch.exe")
        shutil.copy2(os.path.join(base, "python.exe"), relaunch)
        for pattern in ("python3.dll", "python3[0-9][0-9].dll", "vcruntime140*.dll"):
            for dll in glob.glob(os.path.join(base, pattern)):
                shutil.copy2(dll, os.path.join(relaunch_dir, os.path.basename(dll)))
        return relaunch

    def _startup_script_writing(self, workdir, marker):
        """
        A PYTHONSTARTUP script: with no arguments, `start` gives the copied
        python.exe a new console, so it has no script to run and falls into
        the interactive prompt -- which is exactly when PYTHONSTARTUP gets
        read and executed, before the first prompt is shown. Writes the
        relaunch marker, then exits immediately rather than sitting at a
        prompt forever waiting for stdin that will never come.
        """
        path = os.path.join(workdir, "relaunch_startup.py")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("import os\n"
                     f"with open({marker!r}, 'w', encoding='utf-8') as fh:\n"
                     "    fh.write('relaunched')\n"
                     "os._exit(0)\n")
        return path

    def _build_relaunch_cmd(self, workdir, marker):
        """
        The Round 3 fixture, kept only for WindowsFixSuspectDiagnostics'
        informational variant -- this is the shape that failed, so keeping
        it lets CI's log confirm (or rule out) the hypothesis above by
        showing whether *this* still fails while the .exe (production's
        actual shape) succeeds.
        """
        relaunch_dir = os.path.join(workdir, "relaunch (x86) & co^!")
        os.makedirs(relaunch_dir, exist_ok=True)
        relaunch = os.path.join(relaunch_dir, "relaunch.cmd")
        with open(relaunch, "w", encoding="utf-8") as fh:
            fh.write(f'@echo off\necho relaunched> "{marker}"\n')
        return relaunch

    def _log_path_in(self, workdir):
        """
        A settings directory carrying the same category of cmd-meaningful
        characters as `target`/`relaunch` (Round 3, PR #65 review) --
        nothing stops a real Windows username from containing them, and the
        log path is interpolated into the script the same way
        target/relaunch are.
        """
        return os.path.join(workdir, "settings (x86) & co^!", "update.log")

    def _spawn_launcher(self, cfg, workdir, timeout, extra_env=None):
        """
        Returns (completed_process, interpreter, launcher_output, error_output).

        subprocess.run(..., capture_output=True) was the first draft here --
        that uses pipes, and a pipe handle the grandchild cmd.exe ends up
        inheriting would make subprocess.run() itself block until cmd exits
        (masking the "parent exits immediately" premise this whole
        reproduction depends on), while also handing cmd.exe usable std
        handles production never gives it. The real app is a windowed
        PyInstaller exe with no console and no std pipes at all, so this
        starves stdin and redirects stdout/stderr to a real file instead.

        extra_env (Round 4): merged in on top of a copy of this process's
        own environment, so it flows down to every process this launcher's
        Popen chain spawns -- the launcher itself, then cmd.exe (which
        inherits it since launch_swap_script's own Popen call passes no
        env=), then whatever `start "" "{relaunch}"` runs (same
        inheritance). Used to hand a relaunch .exe built by
        _build_relaunch_exe its PYTHONHOME/PYTHONSTARTUP.
        """
        interpreter = self._gui_interpreter()
        launcher_log = os.path.join(workdir, "launcher-output.log")
        error_log = os.path.join(workdir, "launcher-error.log")
        env = dict(os.environ)
        env.update(extra_env or {})
        env["AFK_TEST_ROOT"] = ROOT
        env["AFK_TEST_ERROR_LOG"] = error_log
        env["AFK_TEST_CFG"] = json.dumps(cfg)
        with open(launcher_log, "w", encoding="utf-8") as out:
            proc = subprocess.run([interpreter, "-c", self._LAUNCHER],
                                  env=env, stdin=subprocess.DEVNULL,
                                  stdout=out, stderr=out, timeout=timeout)
        return (proc, interpreter, self._read_or(launcher_log),
                self._read_or(error_log))

    def _read_or(self, path, default=""):
        if path and os.path.exists(path):
            with open(path, encoding="utf-8", errors="replace") as fh:
                return fh.read()
        return default

    def _poll_until(self, predicate, timeout, interval=0.5):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return True
            time.sleep(interval)
        return predicate()

    def _mirrored(self, target):
        return (os.path.isfile(os.path.join(target, "new.txt"))
                and os.path.isfile(os.path.join(target, "sub", "nested.txt"))
                and not os.path.exists(os.path.join(target, "old.txt")))

    def _diagnostics(self, interpreter, launcher_output, error_output):
        # On a timeout, say *why*, not just that it timed out. The caller
        # appends update.log's own contents on top of this -- see phase B's
        # write_swap_script logging -- which is now the strongest evidence
        # for which step actually stalled.
        lines = [
            f"launcher interpreter: {interpreter}",
            f"target mirrored: {self._mirrored(self.target)}",
            f"relaunch marker present: {os.path.exists(self.marker)}",
        ]
        try:
            tasklist = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq cmd.exe"],
                capture_output=True, text=True, timeout=10)
            lines.append(f"tasklist cmd.exe (rc={tasklist.returncode}):\n"
                        f"{tasklist.stdout}{tasklist.stderr}")
        except Exception as exc:
            lines.append(f"tasklist failed: {exc}")
        lines.append(f"launcher stdout/stderr: {launcher_output!r}"
                    if launcher_output else "launcher stdout/stderr: (empty)")
        lines.append(f"launcher crash traceback: {error_output}" if error_output
                    else "launcher crash traceback: (none -- the launcher's "
                        "own try/except never fired)")
        return "\n".join(lines)


@unittest.skipUnless(sys.platform == "win32", "Windows launch reproduction")
class WindowsLaunchReproduction(_SwapScriptLauncher, unittest.TestCase):
    """
    The acceptance case: G#35/GH#63's repro/red-green criterion. Must fail
    on today's `_quit_for_update` and pass once its Windows branch is fixed.

    No @needs_display: this exercises subprocess/write_swap_script, not Tk,
    and Windows always has a window server in CI regardless of DISPLAY.
    """

    def setUp(self):
        self.workdir = tempfile.mkdtemp(prefix="afk-repro-")
        self.addCleanup(shutil.rmtree, self.workdir, ignore_errors=True)
        self.staged, self.target, self.marker = self._fixture_in(self.workdir)
        # Round 4: a real .exe, the same shape as production's actual
        # relaunch target (sys.executable) -- see _build_relaunch_exe's
        # docstring for why Round 3's .cmd fixture was not faithful to
        # production here.
        self.relaunch = self._build_relaunch_exe(self.workdir)
        startup_script = self._startup_script_writing(self.workdir, self.marker)
        self.relaunch_env = {"PYTHONHOME": sys.base_prefix,
                             "PYTHONSTARTUP": startup_script}
        self.log_path = self._log_path_in(self.workdir)

    def tearDown(self):
        self._kill_stragglers()

    def _log_or(self, default="(no log written)"):
        return self._read_or(self.log_path, default)

    def test_production_launch_replaces_the_install_and_relaunches(self):
        # The launcher calls app.launch_swap_script (stdio_mode "production"
        # in _LAUNCHER) -- the exact function _quit_for_update calls, not a
        # hand copy of its flags, so this test can never silently drift from
        # what production actually runs.
        cfg = {"staged": self.staged, "target": self.target,
               "relaunch": self.relaunch, "log_path": self.log_path,
               "creationflags": None, "stdio_mode": "production",
               "keep_alive_seconds": 0}
        proc, interpreter, launcher_output, error_output = self._spawn_launcher(
            cfg, self.workdir, timeout=60, extra_env=self.relaunch_env)
        self.assertEqual(
            proc.returncode, 0,
            f"the launcher subprocess ({interpreter}) exited "
            f"{proc.returncode} before it could even reach Popen(): "
            f"{launcher_output!r}")
        self.assertEqual(
            error_output, "",
            f"the launcher ({interpreter}) raised inside its own "
            f"try/except: {error_output}")

        ok = self._poll_until(
            lambda: self._mirrored(self.target) and os.path.exists(self.marker),
            timeout=45)
        # update.log is now the best evidence on a timeout -- the console
        # this used to flash is gone, so a stalled step only shows up here.
        self.assertTrue(
            ok, self._diagnostics(interpreter, launcher_output, error_output)
            + f"\nupdate.log:\n{self._log_or()}")

        # docs/spec.md's "Shipped update log" acceptance criteria: a
        # successful update's log records the copy step's exit code and
        # ends with done.
        log = self._log_or()
        self.assertIn("copy exit code", log, log)
        non_empty = [line for line in log.splitlines() if line.strip()]
        self.assertTrue(non_empty and non_empty[-1].strip().endswith("done"), log)

    def test_wait_loop_paces_polls_instead_of_busy_spinning(self):
        # The acceptance case above can't prove pacing: its own pid (the
        # launcher's) dies within roughly one mainloop iteration of Popen(),
        # so the wait loop only ever gets to check once. Here the launcher
        # is told to stay alive for a few seconds (keep_alive_seconds)
        # before exiting, which keeps the waited-on pid alive long enough
        # for the loop to actually iterate a handful of times -- if
        # `timeout` were still in the loop and failing outright under a
        # console-less cmd (docs/spec.md's suspect 2), there would be no
        # sleep left at all and the logged iteration count over this many
        # real seconds would be enormous (a busy loop of tasklist calls),
        # not roughly one per second.
        keep_alive_seconds = 5
        cfg = {"staged": self.staged, "target": self.target,
               "relaunch": self.relaunch, "log_path": self.log_path,
               "creationflags": None, "stdio_mode": "production",
               "keep_alive_seconds": keep_alive_seconds}
        proc, interpreter, launcher_output, error_output = self._spawn_launcher(
            cfg, self.workdir, timeout=60 + keep_alive_seconds,
            extra_env=self.relaunch_env)
        self.assertEqual(proc.returncode, 0, launcher_output)
        self.assertEqual(error_output, "", error_output)

        ok = self._poll_until(
            lambda: self._mirrored(self.target) and os.path.exists(self.marker),
            timeout=45)
        log = self._log_or()
        self.assertTrue(ok, self._diagnostics(interpreter, launcher_output, error_output)
                        + f"\nupdate.log:\n{log}")

        match = re.search(r"wait finished after (\d+) iterations", log)
        self.assertIsNotNone(match, f"no 'wait finished' line in the log:\n{log}")
        iterations = int(match.group(1))
        # A generous window either side of "roughly one per second": CI
        # scheduling jitter and tasklist's own spawn cost mean this is never
        # exactly keep_alive_seconds, but a genuine busy-loop (no sleep at
        # all) would produce dozens to hundreds of iterations in the same
        # span, not something in this neighbourhood.
        self.assertGreater(iterations, 0, f"loop never iterated:\n{log}")
        self.assertLess(
            iterations, keep_alive_seconds * 4,
            f"{iterations} iterations while the pid was alive for "
            f"~{keep_alive_seconds}s looks like a busy spin, not a paced "
            f"poll:\n{log}")


@unittest.skipUnless(sys.platform == "win32", "Windows launch reproduction")
class WindowsFixSuspectDiagnostics(_SwapScriptLauncher, unittest.TestCase):
    """
    Not the acceptance case above -- informational only, and must never
    fail the suite on either today's code or the fixed code: their job is
    to be read by a human from the CI log, confirming/recording which of
    the three named suspects (docs/spec.md "Proposed approach" #1) was
    actually the cause, not to gate the build a second time.
    """

    def tearDown(self):
        self._kill_stragglers()

    def test_old_creationflags_still_stall_for_the_record(self):
        # Phase A's CI evidence already narrowed this down: production_flags
        # +captured_stdio came back empty (no "Input redirection is not
        # supported", ruling suspect 2 out as *the* cause) and
        # production_flags+parent_stays_alive still failed (ruling suspect 3
        # out) -- so those two variants no longer teach anything and are not
        # reproduced here. What is left worth keeping on record: replaying
        # the *old*, pre-fix creationflags (DETACHED_PROCESS, no stdio
        # kwargs at all -- the literal original bug) through the *new*
        # logging write_swap_script, so the log file itself -- not a
        # console that never had anywhere to flash -- shows which step it
        # stalls on. The log write is a plain file redirect, not console
        # I/O, so it should still land even if a later console-subsystem
        # step (tasklist/find/ping/robocopy) is the one actually stuck.
        workdir = tempfile.mkdtemp(prefix="afk-repro-diag-")
        self.addCleanup(shutil.rmtree, workdir, ignore_errors=True)
        staged, target, marker = self._fixture_in(workdir)
        relaunch = self._build_relaunch_cmd(workdir, marker)
        log_path = self._log_path_in(workdir)
        cfg = {"staged": staged, "target": target, "relaunch": relaunch,
               "log_path": log_path, "creationflags": self.OLD_CREATIONFLAGS,
               "stdio_mode": "none", "keep_alive_seconds": 0}
        proc, interpreter, launcher_output, error_output = self._spawn_launcher(
            cfg, workdir, timeout=60)
        ok = self._poll_until(
            lambda: self._mirrored(target) and os.path.exists(marker),
            timeout=45)
        log = self._read_or(log_path, "(no log written)")
        # print(), not assert: informational only, see class docstring --
        # this must never fail the suite on either the old or the fixed code.
        print(f"[diagnostic:old_creationflags+no_stdio] interpreter={interpreter} "
              f"succeeded={ok} launcher_rc={proc.returncode} "
              f"launcher_output={launcher_output!r} "
              f"launcher_error={error_output!r}\nupdate.log:\n{log}")

    def test_cmd_relaunch_in_special_char_dir_for_the_record(self):
        """
        Round 4, PR #65 review: informational only, never asserts. Round 3's
        actual CI failure was a `.cmd` relaunch target sitting in a
        `&()^!`-bearing directory -- mirrored fine, `done` written, but no
        relaunch marker and two leftover cmd.exe. The acceptance case above
        no longer uses a `.cmd` relaunch at all (see _build_relaunch_exe's
        docstring for why), so this keeps that exact shape under test, under
        the *fixed* launch flags (production shape, not the old
        creationflags above) -- direct evidence for or against the
        hypothesis that `start "" "<path.cmd>"` needs a nested `cmd /c` to
        run a batch file, and that nested shell's own quote-stripping (strip
        the outer quotes when the string contains `&()^` between them)
        breaks on the `&`.
        """
        workdir = tempfile.mkdtemp(prefix="afk-repro-diag-")
        self.addCleanup(shutil.rmtree, workdir, ignore_errors=True)
        staged, target, marker = self._fixture_in(workdir)
        relaunch = self._build_relaunch_cmd(workdir, marker)
        log_path = self._log_path_in(workdir)
        cfg = {"staged": staged, "target": target, "relaunch": relaunch,
               "log_path": log_path, "creationflags": None,
               "stdio_mode": "production", "keep_alive_seconds": 0}
        proc, interpreter, launcher_output, error_output = self._spawn_launcher(
            cfg, workdir, timeout=60)
        ok = self._poll_until(
            lambda: self._mirrored(target) and os.path.exists(marker),
            timeout=45)
        log = self._read_or(log_path, "(no log written)")
        # print(), not assert: informational only, see class docstring.
        print(f"[diagnostic:cmd_relaunch_in_special_char_dir] "
              f"interpreter={interpreter} succeeded={ok} "
              f"launcher_rc={proc.returncode} "
              f"launcher_output={launcher_output!r} "
              f"launcher_error={error_output!r}\nupdate.log:\n{log}")

    def test_exe_relaunch_probe_from_a_plain_directory_for_the_record(self):
        """
        Coordinator addition ahead of the Round 4 push: runs the exact same
        .exe relaunch probe the acceptance case now uses (copied python.exe
        + DLLs, PYTHONHOME/PYTHONSTARTUP -- see _build_relaunch_exe) but
        from a directory with no special characters at all ("relaunch
        plain"), while keeping `staged`/`target` the same special-char
        shape _fixture_in already builds (robocopy already proven fine
        against that in Round 3 -- `copy exit code 3`). This isolates the
        one variable the acceptance case cannot isolate by itself: whether
        a failure there is about the .exe probe mechanism, or specifically
        about special characters in the *relaunch* path.

        Interpretation, recorded in docs/implementation.md's Round 4
        section once the next CI run reports both results:
          - this succeeds AND the acceptance case (special-char relaunch
            dir) also succeeds -> production handles both; Round 3's
            actual failure was specific to the old .cmd fixture, not to
            special characters as such.
          - this succeeds but the acceptance case fails -> a real
            production bug with special characters in the relaunch path
            specifically.
          - this itself fails -> the .exe probe mechanism (the copy +
            PYTHONHOME/PYTHONSTARTUP chain) is broken, and the acceptance
            case's result is not meaningful until the probe itself is
            fixed.

        In its own class (WindowsFixSuspectDiagnostics), not
        WindowsLaunchReproduction, specifically so it still runs and
        reports even when the acceptance case fails or errors -- unittest
        runs every test method in a module independently regardless of
        another class's outcome, so this needs no special wiring to
        guarantee that.
        """
        workdir = tempfile.mkdtemp(prefix="afk-repro-diag-")
        self.addCleanup(shutil.rmtree, workdir, ignore_errors=True)
        staged, target, marker = self._fixture_in(workdir)
        relaunch = self._build_relaunch_exe(workdir, dir_name="relaunch plain")
        startup_script = self._startup_script_writing(workdir, marker)
        extra_env = {"PYTHONHOME": sys.base_prefix, "PYTHONSTARTUP": startup_script}
        log_path = self._log_path_in(workdir)
        cfg = {"staged": staged, "target": target, "relaunch": relaunch,
               "log_path": log_path, "creationflags": None,
               "stdio_mode": "production", "keep_alive_seconds": 0}
        proc, interpreter, launcher_output, error_output = self._spawn_launcher(
            cfg, workdir, timeout=60, extra_env=extra_env)
        ok = self._poll_until(
            lambda: self._mirrored(target) and os.path.exists(marker),
            timeout=45)
        log = self._read_or(log_path, "(no log written)")
        # print(), not assert: informational only, see class docstring.
        print(f"[diagnostic:exe_relaunch_probe_from_plain_dir] "
              f"interpreter={interpreter} succeeded={ok} "
              f"launcher_rc={proc.returncode} "
              f"launcher_output={launcher_output!r} "
              f"launcher_error={error_output!r}\nupdate.log:\n{log}")


@needs_display
class UpdateLogDetection(unittest.TestCase):
    """update_log_status()/read_update_log() -- G#36/GH#64's read-only
    startup detection, no network, no Tk."""

    def setUp(self):
        self.workdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.workdir, ignore_errors=True)
        self.log_path = os.path.join(self.workdir, "update.log")

    def _write(self, text):
        with open(self.log_path, "w", encoding="utf-8") as fh:
            fh.write(text)

    def test_no_log_file_is_ok(self):
        self.assertEqual(app.update_log_status(self.log_path), "ok")

    def test_read_update_log_returns_none_for_a_missing_file(self):
        self.assertIsNone(app.read_update_log(self.log_path))

    def test_log_without_a_trailing_done_line_is_incomplete(self):
        self._write("2026-01-01 00:00:00 start pid=1 staged=a target=b relaunch=c\n"
                    "2026-01-01 00:00:01 wait finished after 1 iterations\n")
        self.assertEqual(app.update_log_status(self.log_path), "incomplete")

    def test_done_with_no_version_field_is_ok(self):
        self._write("2026-01-01 00:00:00 start pid=1 staged=a target=b relaunch=c\n"
                    "2026-01-01 00:00:01 done\n")
        self.assertEqual(app.update_log_status(self.log_path), "ok")

    def test_done_with_a_matching_version_is_ok(self):
        self._write(
            f'2026-01-01 00:00:00 start pid=1 staged=a target=b relaunch=c version="v{app.__version__}"\n'
            "2026-01-01 00:00:01 done\n")
        self.assertEqual(app.update_log_status(self.log_path), "ok")

    def test_done_with_a_mismatched_version_is_wrong_version(self):
        self._write(
            '2026-01-01 00:00:00 start pid=1 staged=a target=b relaunch=c version="v0.0.1"\n'
            "2026-01-01 00:00:01 done\n")
        self.assertEqual(app.update_log_status(self.log_path), "wrong_version")

    def test_current_version_argument_overrides_the_module_default(self):
        self._write(
            '2026-01-01 00:00:00 start pid=1 staged=a target=b relaunch=c version="v9.9.9"\n'
            "2026-01-01 00:00:01 done\n")
        self.assertEqual(
            app.update_log_status(self.log_path, current_version="9.9.9"), "ok")

    def test_read_update_log_bounds_a_huge_file_to_its_tail(self):
        # "Log absurdly large" -- read_update_log must never load the whole
        # file, only its last 1 MiB.
        with open(self.log_path, "wb") as fh:
            fh.write(b"x" * (2 * 1024 * 1024))
            fh.write(b"TAIL-MARKER")
        text = app.read_update_log(self.log_path)
        self.assertLessEqual(len(text), 1024 * 1024 + len("TAIL-MARKER"))
        self.assertTrue(text.endswith("TAIL-MARKER"))

    def test_read_update_log_replaces_invalid_utf8_bytes_instead_of_raising(self):
        with open(self.log_path, "wb") as fh:
            fh.write(b"2026-01-01 00:00:00 staged=C:\\Users\\caf\xe9 target=b\n")
        text = app.read_update_log(self.log_path)
        self.assertIn("\ufffd", text)


@needs_display
class IssueReportBuilder(unittest.TestCase):
    """build_issue_report()/build_issue_url() -- the redacted preview and
    the prefilled GitHub issue URL, no network."""

    LOG_TEXT = ('2026-01-01 00:00:00 start pid=1 staged="{home}/x" '
               'target="{home}/y" relaunch="{home}/z" version="v0.7.0"\n'
               "2026-01-01 00:00:01 copy exit code 1\n")

    def setUp(self):
        self.home = os.path.expanduser("~")
        self.log_text = self.LOG_TEXT.format(home=self.home)

    def test_title_names_the_target_version_when_known(self):
        title, _body = app.build_issue_report("0.6.0", "v0.7.0", self.log_text)
        self.assertEqual(title, "Update from v0.6.0 to v0.7.0 didn't finish")

    def test_title_falls_back_when_target_version_is_unknown(self):
        title, _body = app.build_issue_report("0.6.0", None, self.log_text)
        self.assertEqual(title, "In-app update didn't finish (v0.6.0)")

    def test_body_names_app_version_target_version_and_os(self):
        _title, body = app.build_issue_report("0.6.0", "v0.7.0", self.log_text)
        self.assertIn("**App version:** 0.6.0", body)
        self.assertIn("**Target version:** v0.7.0", body)
        self.assertIn(app.platform.platform(), body)

    def test_body_names_unknown_target_version_as_older_log_format(self):
        _title, body = app.build_issue_report("0.6.0", None, self.log_text)
        self.assertIn("**Target version:** unknown (older log format)", body)

    def test_redacted_by_default_hides_the_home_directory(self):
        _title, body = app.build_issue_report("0.6.0", "v0.7.0", self.log_text)
        self.assertNotIn(self.home, body)
        self.assertIn("~/x", body)

    def test_redact_false_keeps_the_full_paths(self):
        _title, body = app.build_issue_report("0.6.0", "v0.7.0", self.log_text, redact=False)
        self.assertIn(f"{self.home}/x", body)

    def test_build_issue_url_round_trips_title_and_body(self):
        title, body = app.build_issue_report("0.6.0", "v0.7.0", self.log_text)
        url = app.build_issue_url(title, body)
        self.assertTrue(url.startswith(f"https://github.com/{app.GITHUB_REPO}/issues/new?"))
        query = url.split("?", 1)[1]
        params = dict(pair.split("=", 1) for pair in query.split("&"))
        self.assertEqual(urllib.parse.unquote_plus(params["title"]), title)
        self.assertEqual(urllib.parse.unquote_plus(params["body"]), body)

    def test_a_huge_log_is_truncated_to_stay_under_the_url_cap(self):
        huge_log = "\n".join(f"2026-01-01 00:00:{i:02d} line {i}" for i in range(2000))
        title, body = app.build_issue_report("0.6.0", "v0.7.0", huge_log)
        url = app.build_issue_url(title, body)
        self.assertLessEqual(len(url), 2000)
        self.assertIn("truncated", body)

    def test_truncation_drops_the_oldest_lines_first(self):
        huge_log = "\n".join(f"line {i}" for i in range(2000))
        _title, body = app.build_issue_report("0.6.0", "v0.7.0", huge_log)
        self.assertNotIn("line 0\n", body)
        self.assertIn("line 1999", body)


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
