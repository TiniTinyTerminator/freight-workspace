# vcpkg → freight Migration Guide

How to migrate a project that uses `vcpkg.json` to use `freight.toml` instead.

---

## Quick start

```sh
# One-shot conversion
vcpkg-scraper convert /path/to/my-project --vcpkg-root ~/vcpkg
```

This reads `vcpkg.json` (and optionally the vcpkg baseline for exact
versions) and writes a `freight.toml` next to it.

---

## What the converter does

Given a `vcpkg.json` like:

```json
{
  "dependencies": [
    "zlib",
    "openssl",
    { "name": "boost-filesystem", "platform": "windows" },
    "fmt"
  ]
}
```

The converter:

1. **Resolves versions** from `versions/baseline.json` in the vcpkg repo
   (requires `--vcpkg-root`). Without it, versions default to `"*"`.

2. **Maps platform conditionals** to `[os.*]` sections:
   - `"platform": "windows"` → `[os.windows.dependencies]`
   - `"platform": "!windows"` → `[os.unix.dependencies]`
   - `"platform": "linux"` → `[os.linux.dependencies]`

3. **Probes `CMakeLists.txt`** (if present) for:
   - C/C++ standard (`CMAKE_CXX_STANDARD`, `target_compile_features`)
   - System library requirements (`find_package(Threads)`, `find_package(OpenGL)`, …)

4. **Generates `freight.toml`**:

```toml
[package]
name    = "my-project"
version = "0.1.0"

# TODO: Add [[bin]] / [[lib]] sections

[compiler]
cxx_standard = "c++17"

[dependencies]
zlib    = "1.3.2"
openssl = "3.5.0"
fmt     = "11.1.4"

[os.windows.dependencies]
boost-filesystem = "1.87.0"

[os.linux.dependencies]
linux = { features = ["pthread"] }
```

5. The generated file has a `# TODO: Add [[bin]] / [[lib]] sections`
   comment because source layout isn't derivable from `vcpkg.json`.
   Add a `[[bin]]` or `[[lib]]` section manually.

---

## Mapping reference

### Platform expressions

| vcpkg `platform` | freight section |
|---|---|
| `"windows"` | `[os.windows.dependencies]` |
| `"!windows"` | `[os.unix.dependencies]` |
| `"linux"` | `[os.linux.dependencies]` |
| `"osx"` | `[os.macos.dependencies]` |
| none / always | `[dependencies]` |

### System libraries (from `find_package`)

The cmake probe detects these `find_package` calls and maps them:

| CMake `find_package` | Linux feature | macOS feature |
|---|---|---|
| `Threads` | `pthread` | `pthread` |
| `OpenGL` | `GL` | `-framework OpenGL` |
| `OpenCL` | `OpenCL` | `-framework OpenCL` |
| `X11` | `X11` | — |
| `ALSA` | `asound` | — |
| `Vulkan` | `vulkan` | — |
| `IOKit` | — | `-framework IOKit` |
| `CoreFoundation` | — | `-framework CoreFoundation` |
| `Ws2_32` | — | — (Windows only) |

`find_package` calls inside `if(WIN32)` blocks are mapped to
`[os.windows.dependencies]` automatically.

---

## After conversion

1. Add `[[bin]]` or `[[lib]]` sections to `freight.toml`
2. Make sure a freight registry is available (see `registry-setup.md`)
3. Run `freight build`

If a dependency isn't in the registry yet, add it as a URL dep:

```toml
[dependencies]
mypkg = { url = "https://github.com/owner/mypkg/archive/v1.2.tar.gz", type = "cmake" }
```

---

## Validating stubs before import

Use `freight-build-all` to batch-test all scraped stubs without
importing them into a registry:

```sh
vcpkg-scraper freight-build-all registry-out/ \
    --freight-bin ./target/debug/freight \
    --out /tmp/test-out

# Results in /tmp/test-out/freight-results.log
# Per-package logs in /tmp/test-out/log/freight/{pass,fail}/
```

This creates a minimal test project for each stub and runs
`freight build`. 50/50 pass rate was confirmed for the first
alphabetical batch (7zip through argh).
