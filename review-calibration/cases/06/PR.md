# Nightly pre-release build

Closes #46

Builds every night at 03:00 UTC and publishes a pre-release, so testers always
have yesterday's code without waiting for a tagged release.

Marked `prerelease: true` so it can never be picked up as a stable release, and
the channel name is a dispatch input so a beta line can be cut from the same
workflow without editing it.

## Verification

Dispatched manually; the pre-release appeared with the expected tag.
