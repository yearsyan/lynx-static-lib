# Demo

`lynx_static_demo` is a small Win32 program built by the top-level CMake
project. It links the generated static archive:

```text
out/lynx/Default/lynx_static.lib
```

Build it through the CMake wrapper from the repository root:

```powershell
python scripts\invoke_cmake.py --build --preset demo
```

The executable is written to:

```text
build/cmake-driver/Release/lynx_static_demo.exe
```

The program creates a native Win32 window, enables per-monitor DPI awareness,
creates a LynxView through the public C API, and loads
`resources/demo/main.lynx.bundle`.

The default bundle is built from local source:

```text
demo/bundle/src/index.tsx
```

The build uses the official rspeedy packages synchronized under
`third_party/lynx/node_modules`. `scripts/build_demo_bundle.py` creates
junctions or symlinks into those pinned packages instead of downloading or
resolving new npm dependencies.

The official upstream Windows Explorer target is still available separately:

```powershell
python scripts\invoke_cmake.py --build --preset explorer
```
