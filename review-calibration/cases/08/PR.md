# Export and import a game profile

Closes #48

Writes one game's settings to a `.afkprofile` file in Downloads and reads one
back, so a configuration that works can be handed to someone else.

`temp_copy` makes a scratch copy first, so a malformed import cannot damage the
file the user was given.

## Verification

Exported the Minecraft profile, edited the interval in the file, imported it
back, and the new value appeared in the window.
