# Local Lynx Patches

This directory contains compatibility patches applied on top of the pinned
official Lynx submodule by `scripts/sync_lynx_deps.py`.

We keep these changes as patches instead of committing them inside
`third_party/lynx` because Lynx is an upstream-owned submodule. The main
`lynxlib` repository should pin an official Lynx commit and carry only the
small local deltas needed to build and run the Windows static SDK.

## `0004-desktop-fetch-empty-body-bridge.patch`

This patch fixes the Desktop C++ `lynx.fetch` bridge used by the Windows static
build.

The public fetch wrapper in Lynx core creates a `Request` whose `BodyMixin`
starts with `new ArrayBuffer(0)`. For a GET request this empty body is still
forwarded to `NativeModules.LynxFetchModule.fetch`. In the Windows/Desktop
static build, that empty `ArrayBuffer(0)` crosses the PrimJS/weak-NAPI native
module bridge before `LynxFetchModule::Fetch` is entered. In practice this can
leave the request pending or crash the JS runtime before the registered
`LynxHttpService` is ever called.

Explorer does not provide a Windows `LynxHttpService` example that exercises
this path. The Windows explorer uses `GenericResourceFetcher` for template and
resource loading; Android, iOS, Harmony, and macOS use different platform
bridges or platform HTTP clients.

The patch keeps the public API behavior but makes the bridge tolerant:

- the JS fetch wrapper builds headers without relying on `Object.fromEntries`;
- empty request bodies are omitted instead of passing `ArrayBuffer(0)`;
- streaming metadata is only forwarded when streaming is requested;
- the Desktop C++ `LynxFetchModule` validates optional fields before casting;
- an opt-in `LYNXLIB_FETCH_TRACE=<path>` file trace can be enabled while
  debugging native fetch dispatch.

The libcurl implementation lives in `lynxlib-http`; this patch only makes sure
standard `fetch()` reaches the registered `LynxHttpService`.
