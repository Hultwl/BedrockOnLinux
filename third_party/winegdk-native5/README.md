# WineGDK native Xbox and WinAppSDK file-picker delta

This engine targets WineGDK commit
`75637b674e1f191e65753663c4c0c32bea05ba6e`, on top of the reviewed r12
commit `432f414b251cc6d668404825a1d0f05eca807a70`.

The cumulative delta retains the native GDK identity, XUser, Xbox context and
Realms implementation developed in the earlier native delta. It also implements the
WinAppSDK 1.8 `Microsoft.Windows.Storage.Pickers.FileOpenPicker` runtime class
inside Wine's `windows.storage.dll` for both PE architectures.

The picker implementation provides the exact WinRT ABI used by Minecraft,
including the `Microsoft.UI.WindowId` factory, validated file-type filters,
asynchronous single- and multiple-file selection, immutable result vectors,
cancellation, and `PickFileResult.Path`.
It delegates the desktop UI to Wine's `IFileOpenDialog`; closing the chooser is
reported as a successful null result instead of raising an exception. Async
results and completion delegates have explicit ownership rules to avoid the
use-after-free and reference-cycle hazards found in earlier prototypes.

The former Minecraft process-memory patcher remains removed. Online state
comes from XGame, XUser and XSAPI, while world and skin imports use the native
WinRT picker rather than a package-identity shim.

`SOURCE-SHA256SUMS` pins every source file changed by the cumulative r12 to
native5 delta. The Bullseye builder applies the reviewed r12 delta followed by
this patch when the target commit is unavailable, then verifies the complete
resulting source tree.
