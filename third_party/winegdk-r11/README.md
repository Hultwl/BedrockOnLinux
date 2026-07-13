# WineGDK r11 source delta

The reviewed r11 engine identifies its exact WineGDK source as commit
`670eda2864dcb22d11c7f2c28973214d4755ad2f`. That commit was originally made
locally on top of the public commit
`6b01dd37f55aeb0385bab4b58f7405b3bf2ae386`.

`signin-rdx-guard.patch` vendors the complete one-file delta so the engine can
be rebuilt even before the target commit is reachable from the public remote.
The build script verifies the public base commit, the patch SHA-256, the
resulting `dlls/xgameruntime/main.c` SHA-256, and the target identity recorded
in `bol/config.py` before compiling. Applying the patch produces the same source
bytes as the target commit; it does not create or publish a Git commit.

Once the target commit is public, the builder accepts it directly and verifies
the same resulting source-file hash. The vendored delta remains the independent
reproducibility record used by the 1.3.0 candidate.
