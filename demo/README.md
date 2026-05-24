# Demo

`lynx_static_demo` is a standalone Win32 CMake project. It consumes the
published Conan package:

```text
lynxlib/0.2.2@neuyan/stable
lynxlib-runtime/0.2.2@neuyan/stable
lynxlib-http/0.2.2@neuyan/stable
```

The demo selects the `lynxlib` `dev` flavor, so the linked static library embeds
`lynx_core_dev.js` and enables inspector/devtool switches. Production generated
projects use the `prod` flavor by default.

Install dependencies and configure from this directory:

```powershell
python ..\scripts\build_demo_bundle.py
conan install . -pr:a profiles/windows-msvc-static -r neuyan --build=missing
cmake --preset windows-release
cmake --build --preset windows-release
```

Run those direct commands from an x64 Visual Studio developer shell.

From the repository root you can run the wrapper:

```powershell
python scripts\build_conan_demo.py
```

The executable is written to:

```text
demo/build/Release/lynx_static_demo.exe
```

The compile commands database is generated at:

```text
demo/build/Release/compile_commands.json
```

The program creates a native Win32 window, enables per-monitor DPI awareness,
creates a LynxView through the public C API, and loads
`resources/demo/main.lynx.bundle`.

Only `icudtl.dat` is copied next to the executable. The Lynx core JS is linked
inside `lynx_static.lib`.

It also registers `lynxlib::http::RegisterCurlHttpService()` on startup. The
bundle has an HTTP service panel that calls `fetch` and displays the result.

The runtime bundle is generated here:

```text
demo/bundle/dist/main.lynx.bundle
```

The bundle source remains here for refreshes:

```text
demo/bundle/src/index.tsx
```

Refreshing the bundle uses the official rspeedy packages synchronized under the
top-level `third_party/lynx/node_modules`. The wrapper command
`python scripts\build_conan_demo.py` builds the bundle before configuring the
standalone demo.

The official upstream Windows Explorer target is still available separately:

```powershell
python scripts\invoke_cmake.py --build --preset explorer
```
