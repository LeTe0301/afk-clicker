"""Version resolution, asset selection, staging and the swap script."""
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import hashlib
import pathlib
import unittest
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
        # And it must clear the old installation first. Without this line the
        # update is a copy-over: every file dropped between releases survives
        # forever, and nothing else in the suite notices.
        if app.sys.platform == "win32":
            self.assertIn("/MIR", body, "robocopy would not prune the old build")
        else:
            self.assertIn("-mindepth 1 -delete", body,
                          "the old installation is never cleared")


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

    # Mirrors _quit_for_update's exact Windows launch line (afk_clicker.py
    # :2982-2983) as a named constant, so the acceptance case below cannot
    # silently drift from what production actually passes to Popen.
    PRODUCTION_CREATIONFLAGS = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    CREATE_NO_WINDOW = 0x08000000

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
    script = app.write_swap_script(cfg["staged"], cfg["target"], cfg["relaunch"])

    kwargs = {"creationflags": cfg["creationflags"]}
    log = None
    if cfg["stdio_mode"] == "devnull":
        kwargs["stdin"] = subprocess.DEVNULL
        kwargs["stdout"] = subprocess.DEVNULL
        kwargs["stderr"] = subprocess.DEVNULL
    elif cfg["stdio_mode"] == "captured":
        # Diagnostic only (WindowsFixSuspectDiagnostics) -- captures what,
        # if anything, the console commands print. Never used by the
        # acceptance case: giving cmd.exe usable stdio handles when
        # production gives it none is plausibly the very thing that changes
        # the outcome (suspects 1/2 are about console/handle availability),
        # so the acceptance case cannot carry this without risking a false
        # green on buggy code.
        log = open(cfg["cmd_log"], "w", encoding="utf-8")
        kwargs["stdout"] = log
        kwargs["stderr"] = log
    # stdio_mode == "none": no stdio kwargs at all -- the exact line
    # _quit_for_update runs (afk_clicker.py:2982-2983).

    subprocess.Popen(["cmd", "/c", script], **kwargs)
    if log is not None:
        log.close()

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
        staged/target/relaunch laid out the way download_and_stage and
        install_root hand them to write_swap_script in production. `target`
        and `relaunch` each sit under a directory with a space in the name
        (real installs land in "Program Files") to guard the existing
        `start "" "{relaunch}"` quoting from a regression, not just test the
        happy path.
        """
        staged = os.path.join(workdir, "staged")
        os.makedirs(os.path.join(staged, "sub"))
        with open(os.path.join(staged, "new.txt"), "w", encoding="utf-8") as fh:
            fh.write("new")
        with open(os.path.join(staged, "sub", "nested.txt"), "w", encoding="utf-8") as fh:
            fh.write("nested")

        target = os.path.join(workdir, "target dir")
        os.makedirs(target)
        with open(os.path.join(target, "old.txt"), "w", encoding="utf-8") as fh:
            fh.write("old")

        relaunch_dir = os.path.join(workdir, "relaunch dir")
        os.makedirs(relaunch_dir)
        marker = os.path.join(workdir, "relaunched.marker")
        relaunch = os.path.join(relaunch_dir, "relaunch.cmd")
        with open(relaunch, "w", encoding="utf-8") as fh:
            fh.write(f'@echo off\necho relaunched> "{marker}"\n')
        return staged, target, relaunch, marker

    def _spawn_launcher(self, cfg, workdir, timeout):
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
        """
        interpreter = self._gui_interpreter()
        launcher_log = os.path.join(workdir, "launcher-output.log")
        error_log = os.path.join(workdir, "launcher-error.log")
        env = dict(os.environ)
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
        # This is the actual point of phase A: on a timeout, say *why*, not
        # just that it timed out -- that is what turns a red run into
        # evidence for one of the three suspects in docs/spec.md. No cmd.exe
        # output to show here -- the acceptance case never captures it (see
        # _LAUNCHER's comment on stdio_mode "none"); that capture only
        # happens in WindowsFixSuspectDiagnostics's own "captured_stdio"
        # variant.
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
        (self.staged, self.target, self.relaunch,
         self.marker) = self._fixture_in(self.workdir)

    def tearDown(self):
        self._kill_stragglers()

    def test_production_launch_replaces_the_install_and_relaunches(self):
        # _quit_for_update's exact command, creationflags, and stdio (none
        # at all -- see _LAUNCHER's stdio_mode "none" branch), the launcher
        # exiting immediately. No other kwargs: this must be byte-identical
        # to afk_clicker.py:2982-2983, or a captured-stdio artefact could
        # turn this green on unfixed code (see _LAUNCHER's "captured" comment).
        cfg = {"staged": self.staged, "target": self.target,
               "relaunch": self.relaunch, "cmd_log": None,
               "creationflags": self.PRODUCTION_CREATIONFLAGS,
               "stdio_mode": "none", "keep_alive_seconds": 0}
        proc, interpreter, launcher_output, error_output = self._spawn_launcher(
            cfg, self.workdir, timeout=60)
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
        self.assertTrue(
            ok, self._diagnostics(interpreter, launcher_output, error_output))


@unittest.skipUnless(sys.platform == "win32", "Windows launch reproduction")
class WindowsFixSuspectDiagnostics(_SwapScriptLauncher, unittest.TestCase):
    """
    Not the acceptance case above -- these isolate which of the three named
    suspects (docs/spec.md "Proposed approach" #1) is the real one, and only
    ever report their outcome. They must never fail the suite, on either
    today's code or the fixed code: their job is to be read by a human from
    the CI log, not to gate the build a second time.
    """

    def tearDown(self):
        self._kill_stragglers()

    def test_diagnostic_variants(self):
        variants = [
            # Suspect 1/2: a real (hidden) console instead of none at all,
            # so cmd/tasklist/timeout/robocopy never need to allocate their
            # own -- the standard shape for "run a console command with no
            # visible window".
            ("create_no_window+devnull_stdio", self.CREATE_NO_WINDOW, "devnull"),
            # What the acceptance case cannot carry (see its own comment):
            # production's exact flags, but with cmd.exe's stdout/stderr
            # captured to a file, to see what -- if anything -- tasklist/
            # timeout/robocopy actually print.
            ("production_flags+captured_stdio", self.PRODUCTION_CREATIONFLAGS, "captured"),
            # Suspect 3: production's exact flags and stdio, but the
            # launcher (this test's stand-in for the app process) stays
            # alive for a few seconds instead of exiting immediately after
            # Popen().
            ("production_flags+parent_stays_alive", self.PRODUCTION_CREATIONFLAGS, "none"),
        ]
        for name, flags, stdio_mode in variants:
            keep_alive = 5 if name == "production_flags+parent_stays_alive" else 0
            with self.subTest(variant=name):
                workdir = tempfile.mkdtemp(prefix="afk-repro-diag-")
                self.addCleanup(shutil.rmtree, workdir, ignore_errors=True)
                staged, target, relaunch, marker = self._fixture_in(workdir)
                cmd_log = (os.path.join(workdir, "cmd-output.log")
                          if stdio_mode == "captured" else None)
                cfg = {"staged": staged, "target": target, "relaunch": relaunch,
                       "creationflags": flags, "stdio_mode": stdio_mode,
                       "cmd_log": cmd_log, "keep_alive_seconds": keep_alive}
                proc, interpreter, launcher_output, error_output = self._spawn_launcher(
                    cfg, workdir, timeout=60 + keep_alive)
                ok = self._poll_until(
                    lambda: self._mirrored(target) and os.path.exists(marker),
                    timeout=45)
                cmd_output = (self._read_or(cmd_log) if cmd_log
                             else "(not captured in this variant)")
                # print(), not assert: informational only, see class docstring.
                print(f"[diagnostic:{name}] interpreter={interpreter} "
                      f"succeeded={ok} launcher_rc={proc.returncode} "
                      f"launcher_output={launcher_output!r} "
                      f"launcher_error={error_output!r} "
                      f"cmd_output={cmd_output!r}")


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
