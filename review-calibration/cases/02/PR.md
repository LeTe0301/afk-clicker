# Add a Card widget for the sidebar

Closes #42

Draws each game as a small card rather than a dot and a label, and adds a
"test this profile" button that clicks once so you can see it working before
committing to a session.

`tk.Canvas` rather than `tk.Frame` because the design calls for rounded
corners, which `Frame` cannot draw.

## Verification

Rendered under Xvfb; the card draws and the running colour switches. The probe
click lands in the target window.
