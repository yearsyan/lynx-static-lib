# lynxlib

`lynxlib` packages the official Lynx Windows runtime as a static-library based
embedder distribution.

The repository wraps the upstream Lynx source tree in `third_party/lynx`, drives
its pinned dependency sync and GN/Ninja Windows build through CMake/Python
helpers, and publishes the resulting artifacts as Conan packages for native
Windows apps.

It includes:

- a static `lynxlib` package with embedded Lynx core JS;
- a small `lynxlib-runtime` package for runtime assets such as ICU data;
- an optional `lynxlib-http` package that registers a libcurl-backed
  `LynxHttpService`;
- a standalone Win32 demo under `demo/` that consumes the packages through
  Conan.

Operational notes for coding agents live in [`agent.md`](agent.md).
