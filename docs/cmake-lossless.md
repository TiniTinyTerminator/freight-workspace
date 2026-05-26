# cmake-lossless — CMake AST Library

A Rust library for parsing CMake files into a typed AST and re-emitting
them without loss of structure.  Used by `freight migrate cmake` and the
vcpkg converter's cmake probe.

---

## Backend

Uses **tree-sitter-cmake** as the parsing backend.  tree-sitter gives a
concrete syntax tree (CST) for the full CMake grammar; cmake-lossless
translates it into a higher-level typed AST that's easier to traverse.

---

## Core types

```rust
pub struct CMakeFile {
    pub nodes: Vec<Node>,
}

pub enum Node {
    Command(CommandInvocation),
    If(IfBlock),
    Foreach(ForeachLoop),
    While(WhileLoop),
    Function(FunctionDef),
    Macro(MacroDef),
    Block(BlockDef),
    Comment(String),
}

pub struct CommandInvocation {
    pub name: String,         // lowercase, e.g. "set", "find_package"
    pub args: Vec<Arg>,
}

pub struct Arg {
    pub value: String,        // decoded (escape sequences resolved)
    pub kind: ArgKind,
}

pub enum ArgKind {
    Unquoted,
    Quoted,
    Bracket,
}

pub struct IfBlock {
    pub condition: Vec<Arg>,
    pub then_nodes: Vec<Node>,
    pub elseif_branches: Vec<(Vec<Arg>, Vec<Node>)>,
    pub else_nodes: Option<Vec<Node>>,
}
```

---

## Parsing

```rust
let file: CMakeFile = cmake_lossless::parse(src)?;
// Returns Err with a ParseError if the file has syntax errors.
// ParseError.message is the error description.
// ParseError.has_error is true if tree-sitter found ERROR nodes.
```

---

## Walking commands

```rust
// Flat iterator over all Command nodes at any depth.
// Skips Function/Macro/Comment wrappers.
for cmd in file.all_commands() {
    let args: Vec<&str> = cmd.arg_values().collect();
    match cmd.name.as_str() {
        "find_package" => { … }
        "set"          => { … }
        _ => {}
    }
}
```

---

## Platform conditions (`eval` module)

```rust
use cmake_lossless::eval;

// Returns the platform scope for an if-block condition.
let scope: Option<&'static str> = eval::platform_condition(&block.condition);
```

| CMake condition | Returns |
|---|---|
| `WIN32` | `Some("windows")` |
| `UNIX` | `Some("unix")` |
| `APPLE` | `Some("macos")` |
| `CMAKE_SYSTEM_NAME STREQUAL Linux` | `Some("linux")` |
| `NOT WIN32`, `MSVC`, unknown | `None` |

Used by the vcpkg converter to route `find_package` calls inside
`if(WIN32)` / `if(UNIX)` blocks to the correct `[os.*]` section.

---

## Variable collection (`vars` module)

```rust
use cmake_lossless::vars;

// Collect all set(VAR VALUE) calls at the top level.
let vars: HashMap<&str, Vec<&str>> = vars::collect(&file);
let ver = vars.get("PROJECT_VERSION").and_then(|v| v.first());
```

---

## Re-emission (`emit` module)

```rust
use cmake_lossless::emit::{emit, EmitOptions};

let out: String = emit(&file, &EmitOptions::default());
// Produces valid CMake with normalized indentation.
// Comments are preserved inline.
```

---

## Error handling invariants

| Situation | Behaviour |
|---|---|
| Well-formed file | `Ok(CMakeFile)` |
| Syntax errors present | `Err(ParseError { has_error: true, … })` |
| I/O error reading file | `Err(ParseError { … })` with message |
| `if` without `endif` | ERROR node → parse error |
| Unknown commands | `Node::Command` with the name preserved |

---

## Open work (from TODO.md)

- VERSION operators in `if()` conditions (`VERSION_LESS`, `VERSION_GREATER_EQUAL`, …)
- Compound platform conditions (`if(UNIX AND NOT APPLE)`)
- `option()` tracking → emit `[features]` in freight.toml
- `list(APPEND)` / `string()` for variable propagation
- `include()` / `add_subdirectory()` following for multi-file projects
- Lossless whitespace preservation (current: re-normalised on emit)
