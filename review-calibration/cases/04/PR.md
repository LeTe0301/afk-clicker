# Warn when a hotkey is already taken by the system

Closes #44

Checks the recorded combination against a list of combinations the operating
system claims, so the user learns now instead of discovering mid-session that
Alt+F4 closes the window instead of toggling the clicker.

The tests are conditional on an input backend being available, so they degrade
gracefully in environments without one rather than failing the build.

## Verification

Both tests pass locally.
