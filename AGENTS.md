# Agent Notes

Use this file for build, packaging, and repo-operation details. Keep
`README.md` high level.

## Project Shape

- This repo is a CMake/Python wrapper around the official Lynx source tree in
  `third_party/lynx`.
- The official Lynx submodule is pinned; do not casually update it or generated
  dependency trees.
- Local compatibility patches live in `patches/lynx` and are applied after the
  official dependency sync.
- Main wrapper scripts live in `scripts/`.
- Build output is under `out/`, `build/`, `demo/build/`, and
  `demo/bundle/dist/`; these are ignored.

## Platform And Toolchain

- Current build support is Windows x86_64 only.
- The official Lynx Windows build uses Visual Studio 2022 LLVM/clang-cl, not
  plain `cl.exe`.
- Required VS components:
  - `Microsoft.VisualStudio.Component.VC.Llvm.Clang`
  - `Microsoft.VisualStudio.Component.VC.Llvm.ClangToolset`
- The scripts usually locate VS, CMake, Ninja, and set the environment
  themselves. Direct demo commands should be run from an x64 Visual Studio
  developer shell.

## Bootstrap

```powershell
git submodule update --init --recursive
python scripts/invoke_cmake.py --preset windows
python scripts/invoke_cmake.py --build --preset deps
```

`deps` downloads the pinned Habitat tool, runs the official Lynx dependency
sync, and applies `patches/lynx`.

## Common Builds

Build the official SDK package:

```powershell
python scripts/invoke_cmake.py --build --preset sdk
```

Build the static archive:

```powershell
python scripts/invoke_cmake.py --build --preset static
```

Build specific static flavors:

```powershell
python scripts/invoke_cmake.py --build --preset static-prod
python scripts/invoke_cmake.py --build --preset static-dev
```

Direct script equivalents:

```powershell
python scripts/build_lynx.py --target static --flavor prod --out-dir out/lynx/Prod --skip-deps
python scripts/build_lynx.py --target static --flavor dev --out-dir out/lynx/Dev --skip-deps
```

Expected static archives:

```text
out/lynx/Prod/lynx_static.lib
out/lynx/Dev/lynx_static.lib
```

`prod` embeds `lynx_core.js` and disables inspector. `dev` embeds
`lynx_core_dev.js` and enables inspector/devtool startup switches.

Build the upstream Windows Explorer demo:

```powershell
python scripts/invoke_cmake.py --build --preset explorer
```

Build all official wrapper targets:

```powershell
python scripts/invoke_cmake.py --build --preset all
```

`all` builds the official SDK, static archive, and upstream Explorer demo. It
does not build the standalone Conan demo.

## Conan Packages

Default references:

```text
lynxlib/0.2.2@neuyan/stable
lynxlib-runtime/0.2.2@neuyan/stable
lynxlib-http/0.2.2@neuyan/stable
```

Export `lynxlib` and `lynxlib-runtime` after the static build:

```powershell
python scripts/package_conan.py --skip-build --version 0.2.2 --flavor prod
python scripts/package_conan.py --skip-build --version 0.2.2 --flavor dev
```

Upload them:

```powershell
python scripts/package_conan.py --skip-build --upload --version 0.2.2 --remote neuyan
```

CMake preset shortcuts:

```powershell
python scripts/invoke_cmake.py --build --preset conan-export
python scripts/invoke_cmake.py --build --preset conan-upload
```

Create the optional HTTP package:

```powershell
python scripts/package_http_conan.py --version 0.2.2
```

Upload it:

```powershell
python scripts/package_http_conan.py --version 0.2.2 --upload --remote neuyan
```

CMake preset shortcuts:

```powershell
python scripts/invoke_cmake.py --build --preset http-conan-create
python scripts/invoke_cmake.py --build --preset http-conan-upload
```

`lynxlib-http` links `lynxlib` and Conan `libcurl`, uses Schannel TLS and
c-ares DNS by default, and only permits `http` and `https` URLs at runtime.

Consumer CMake usage:

```cmake
find_package(lynxlib_http CONFIG REQUIRED)
target_link_libraries(my_app PRIVATE lynxlib_http::lynxlib_http)
```

Consumer startup registration:

```cpp
#include "lynxlib/http_service.h"

lynxlib::http::RegisterCurlHttpService();
```

## Standalone Demo

Build the demo through the wrapper:

```powershell
python scripts/build_conan_demo.py
```

Direct commands from `demo/`:

```powershell
python ..\scripts\build_demo_bundle.py
conan install . -pr:a profiles/windows-msvc-static -r neuyan --build=missing
cmake --preset windows-release
cmake --build --preset windows-release
```

Expected outputs:

```text
demo/build/Release/lynx_static_demo.exe
demo/build/Release/compile_commands.json
demo/bundle/dist/main.lynx.bundle
```

Verify the demo static link and smoke run:

```powershell
python scripts/verify_demo.py
```

The standalone demo consumes `lynxlib`, `lynxlib-runtime`, and `lynxlib-http`
from Conan. It loads the generated `demo/bundle/dist/main.lynx.bundle` and
registers the curl HTTP service.

Build the generated demo bundle:

```powershell
python scripts/build_demo_bundle.py
```

## Generated App Projects

`scripts/lynx_project.py` creates and manages generated Conan-based Lynx app
projects.

Useful commands:

```powershell
python scripts/lynx_project.py init path\to\app --name MyApp
python scripts/lynx_project.py build path\to\app
python scripts/lynx_project.py build path\to\app --export
python scripts/lynx_project.py export path\to\app
```

Generated projects use `lynx_project.json` for package refs, flavor, bundle
embedding, runtime asset copying, and compile command export.

## Inspector / Devtool

Use the `dev` flavor when inspector support is needed. Host apps can connect
the debug router through the public embedder API:

```cpp
auto& env = lynx::pub::LynxEnv::GetInstance();
env.SetDevtoolEnabled(true);
env.ConnectDevtool(
    "lynx://remote_debug_lynx/enable?url=ws://127.0.0.1:xxxx&room=<room-id>");
```

The current upstream Windows Explorer enables devtool but does not hard-code a
websocket connection URL.

## Git Hygiene

- Do not commit `out/`, `build/`, downloaded Habitat cache, local logs, or
  generated Lynx dependencies.
- Commit wrapper files, `.gitmodules`, the submodule pointer, source changes,
  and patches.
- Do not commit generated demo bundles under `demo/bundle/dist/`.
- Before editing, check `git status --short`; preserve unrelated user changes.
