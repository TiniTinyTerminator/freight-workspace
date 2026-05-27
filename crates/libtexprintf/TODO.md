# TODO — libtexprintf Rust binding

## Open

- Add pkg-config probing in `build.rs` so installed `libtexprintf` locations are
  detected without requiring `TEXPRINTF_LIB_DIR`.
- Add a native smoke test that runs only when `libtexprintf` is installed on the
  host or CI image.
- Decide whether this crate should be split into its own repository/submodule
  once the API settles.

## Done

- Initial safe wrapper around `stexprintf`.
- Default build avoids native linking; `native` feature links `-ltexprintf`.
- Escape `%` before passing user input into the printf-style C API.
