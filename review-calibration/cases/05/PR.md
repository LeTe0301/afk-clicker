# Smooth the reported click rate

Closes #45

The instantaneous rate jumped around too much to read. This keeps the last
twenty timestamps and reports the average over that window.

Two tests: one checks the rate against a known interval, one checks the window
stays bounded so memory cannot grow during a long session.

## Verification

Both tests pass. The rate reads steady at 1.96/s for a 510 ms interval.
