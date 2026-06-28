//! `freight-migrate` — migrate foreign (CMake) C/C++ projects into freight manifests.
//!
//! This is a separate tool, decoupled from the freight build engine. Auto-generating
//! a manifest from an arbitrary C++ project is best-effort and easy to get subtly
//! wrong, so it lives outside `freight` itself; the safe, supported path for building
//! a foreign project is a `build = "cmake"` manifest (hand-written or adopted here),
//! built by freight's cmake plugin with the real cmake tool.
pub mod adopt;
pub mod cmake_scan;
pub mod fileapi;
pub mod native;
