# Answer key — case 02

## Planted defects

| id | Round | Severity | Defect |
|---|---|---|---|
| 02-a | 4 | BLOCKER | `class Card` shadows the module-level colour constant `CARD`? No — worse and more subtle: this module already imports `Button` from `pynput.mouse`, and any file that later defines a Tk widget class named `Button` will shadow it. Here the same pattern is one step away: `Card` is fine, but `ProfileTester` imports `Button` into a module whose whole purpose is Tk widgets, so the next widget class named `Button` silently breaks every mouse call. The import must be aliased (`MouseButton`) as the project already does elsewhere. |
| 02-b | 6 | CONCERN | The module imports `pynput.mouse` into a widget module, mixing the input layer into the UI layer. `TECHSTACK.md` keeps them apart for a reason: PyInstaller hidden imports are tracked per backend. |
| 02-c | 2 | CONCERN | `set_running` only recolours the title; the card has no icon and no state dot, so it does not do what the PR says it does. |
| 02-d | 8 | CONCERN | No test. "Rendered under Xvfb" is a manual check. |
| 02-e | 5 | CONCERN | `profile["name"]` is indexed without a default; a profile added from a foreground window title that failed to read would raise at construction. |

## Deliberate non-defects

| id | Looks wrong because | Why it is right |
|---|---|---|
| 02-x | `tk.Canvas` for something a `Frame` could hold | Correct and explained: `Frame` cannot draw rounded corners, and the project draws them on canvases everywhere. |
| 02-y | The colour constants are duplicated rather than imported | A calibration case is a standalone file; in the real module they come from the palette. Not a finding. |

## Scoring

The essential finding is 02-a: the aliasing rule exists in
`CODING-GUIDELINES.md` precisely because `Button` shadowed `pynput.mouse.Button`
once already. A reviewer who reads the guidelines and does not connect them to
this import has read them without using them.
