# Freight — Documentation Index

| Document | Contents |
|---|---|
| [architecture.md](architecture.md) | Full system architecture: build pipeline, registry wire format, dep resolution chain, all crates |
| [registry-setup.md](registry-setup.md) | How to run a freight registry, import vcpkg packages, and configure clients |
| [vcpkg-migration.md](vcpkg-migration.md) | How to convert a vcpkg.json project to freight.toml |
| [cmake-lossless.md](cmake-lossless.md) | cmake-lossless API reference (AST types, eval, vars, emit) |

---

## Quick orientation

Freight is a Cargo-inspired build tool for C, C++, Fortran, CUDA and
other compiled languages.  A single `freight.toml` replaces CMakeLists,
Makefiles, and `vcpkg.json`.

**New to freight?** Start with [architecture.md](architecture.md) to
understand how the build pipeline works, then [registry-setup.md](registry-setup.md)
to run a local registry.

**Migrating from vcpkg?** See [vcpkg-migration.md](vcpkg-migration.md).

**Working on the cmake parser?** See [cmake-lossless.md](cmake-lossless.md).
