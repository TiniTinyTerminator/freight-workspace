# libtexprintf Rust binding

Small Rust wrapper for [`bartp5/libtexprintf`](https://github.com/bartp5/libtexprintf).

The crate builds without the native library by default. Enable `native` to link
against `libtexprintf` and render TeX-like math to monospace UTF-8 text:

```rust
let rendered = libtexprintf::render(r"\frac{\alpha}{\beta+x}")?;
```

When `native` is enabled, the build script first tries `TEXPRINTF_LIB_DIR`, then
`pkg-config` for `texprintf.pc`. If neither is available, it clones
`https://github.com/bartp5/libtexprintf.git` into Cargo's build output directory
and builds a static `libtexprintf.a` with autotools.

For offline builds, set `TEXPRINTF_SOURCE_DIR` to a local libtexprintf checkout
or release tree. If the source tree has no `configure` script, the build script
runs `autoreconf -fi` before configuring. The source build requires `git`,
`make`, a C compiler, and autotools/libtool when bootstrapping from a raw
checkout.

The upstream C library is GPL-3.0. Keep consumers behind an explicit feature if
they do not want to always link that dependency.
