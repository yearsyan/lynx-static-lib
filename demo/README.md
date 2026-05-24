# Demo

`lynx_static_demo` is a standalone Win32 CMake project. It consumes the
published Conan package:

```text
lynxlib/0.2@neuyan/stable
lynxlib-runtime/0.2@neuyan/stable
lynxlib-http/0.2@neuyan/stable
```

Install dependencies and configure from this directory:

```powershell
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

It also registers `lynxlib::http::RegisterCurlHttpService()` on startup. The
bundle has an HTTP service panel that calls `fetch` and displays the result.

The default runtime bundle is checked in here:

```text
demo/bundle/dist/main.lynx.bundle
```

The bundle source remains here for refreshes:

```text
demo/bundle/src/index.tsx
```

Refreshing the bundle uses the official rspeedy packages synchronized under the
top-level `third_party/lynx/node_modules`, but building this standalone demo
does not require that tree once the Conan package and prebuilt bundle exist.

The official upstream Windows Explorer target is still available separately:

```powershell
python scripts\invoke_cmake.py --build --preset explorer
```
