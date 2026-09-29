# Remember the window position

Closes #43

Stores the window geometry in settings.json and restores it at startup.

`load_geometry` is defensive: anything malformed in the stored blob is caught
and the window falls back to its default position, so a damaged settings file
can never stop the program from opening.

## Verification

Moved the window, restarted, it came back in place. Hand-edited the config to
garbage and it started normally.
