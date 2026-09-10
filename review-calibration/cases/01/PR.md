# Add a live click counter

Closes #41

Shows the number of clicks and the current rate in the status pill, so you can
see at a glance whether the farm is still producing.

The counter runs on its own thread so the count stays smooth even while the
window is being dragged, and reads the interval from the field each pass so
changing it mid-session is reflected immediately.

`time.monotonic()` rather than `time.time()`, so a clock adjustment during a
long session cannot make the rate negative.

## Verification

Ran it for twenty minutes against the Minecraft profile; the count matched the
number of clicks in the log and the rate settled at 1.96/s for a 510 ms
interval.
