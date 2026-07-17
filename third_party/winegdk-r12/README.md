# WineGDK r12 source delta

The r12 engine targets WineGDK commit
`432f414b251cc6d668404825a1d0f05eca807a70`, on top of public commit
`e75ddb5f5d8874eecf8e8c1742e6aaa4db9cd4a3`.

The public base already contains the XAsync/XTaskQueue lifetime fixes needed
by Minecraft's networking callbacks. `online-patches-after-user-ready.patch`
adds the issue #31 fix: it removes the early code-cave trampoline that could
dereference the transient pointer `0xff` (and fault while reading `0x107`),
waits for complete XUser multiplayer credentials, and then atomically applies
only fingerprinted XblInitialize and server-join branch patches for supported
Minecraft builds.

`SOURCE-SHA256SUMS` pins every source file changed by the delta. The Bullseye
builder verifies the base or target commit, the vendored patch, and these
resulting file hashes before compiling. Applying the patch does not mutate the
caller's WineGDK checkout.
