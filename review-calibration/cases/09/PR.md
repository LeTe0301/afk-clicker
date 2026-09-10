# Refuse to start when nothing has focus

Closes #49

Clicking into the desktop does nothing useful and can drop a held item, so the
loop now checks that a window has focus before starting.

Also fixes a bug found while writing this: `session_log_path` could return a
path directly under the filesystem root. It now builds under a dedicated
directory in the system temp location, and there is a test for it.

## Verification

Four tests, all passing.
