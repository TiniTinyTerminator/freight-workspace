#!/usr/bin/env python3
"""
Compare Freight's embedded Fortran LSP path against fortls on a small fixture.

The script is intentionally narrow and deterministic: it exercises the core
fortls-owned requests that Freight is replacing, normalizes volatile JSON fields,
and reports mismatches. It does not require Freight to launch fortls.

Usage:
    python3 scripts/fortran_lsp_compare.py --freight target/debug/freight
    python3 scripts/fortran_lsp_compare.py --fortls python3 -m fortls
"""

from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import select
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

WORKSPACE = Path(__file__).resolve().parent.parent
FORTLS_REFERENCE = Path("/tmp/fortls-reference")

MODULE_SOURCE = """module math
interface
module subroutine axpy(a, x, y)
real :: a
real :: x
real :: y
end subroutine
end interface
contains
subroutine saxpy(a, x, y)
real :: a
real :: x
real :: y
y = a*x + y
end subroutine
end module
"""

SUBMODULE_SOURCE = """submodule (math) math_impl
contains
module procedure axpy
y = a*x + y
end procedure
end submodule
"""

APP_SOURCE = """program app
use math, only: axpy, saxpy
real :: a, x, y
call axpy(a, x, y)
call saxpy(a, x, y)
end program
"""

BAD_SOURCE = """program bad
use missing_mod
call missing_proc()
end program
"""

ACTION_SOURCE = """module shapes
type, abstract :: shape
contains
procedure(draw_iface), deferred :: draw
end type
type, extends(shape) :: circle
end type
end module
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--freight", default=str(WORKSPACE / "target/debug/freight"))
    parser.add_argument(
        "--fortls",
        nargs="+",
        default=[sys.executable, "-m", "fortls"],
        help="fortls command, e.g. --fortls python3 -m fortls",
    )
    parser.add_argument(
        "--project",
        type=Path,
        help="Run a real-project comparison by copying this directory to a temp root.",
    )
    parser.add_argument(
        "--max-files",
        type=int,
        default=0,
        help="In --project mode, compare at most this many sorted Fortran files. 0 means all files.",
    )
    parser.add_argument(
        "--open-only",
        help="In --project mode, open ONLY files whose relative path contains this "
        "substring (the rest of the tree stays on disk for both servers to index). "
        "This is the single-open-file mode: it exercises workspace-level indexing "
        "that opening every file structurally hides — e.g. resolving a `use` of a "
        "module whose file was never opened.",
    )
    parser.add_argument(
        "--request-timeout",
        type=float,
        default=20.0,
        help="Seconds to wait for each LSP request before failing.",
    )
    parser.add_argument(
        "--diagnostic-timeout",
        type=float,
        default=2.0,
        help="Seconds to collect publishDiagnostics notifications after opening files.",
    )
    parser.add_argument(
        "--diagnostic-quiet",
        type=float,
        default=2.0,
        help="Stop collecting diagnostics after all files reported and no new diagnostic arrives for this many seconds.",
    )
    parser.add_argument(
        "--settle-delay",
        type=float,
        default=0.2,
        help="Seconds to pause after diagnostics before issuing symbol/query requests.",
    )
    parser.add_argument("--keep-fixture", action="store_true")
    parser.add_argument("--verbose", "-v", action="store_true")
    return parser.parse_args()


def encode(msg: dict[str, Any]) -> bytes:
    body = json.dumps(msg, separators=(",", ":")).encode()
    return f"Content-Length: {len(body)}\r\n\r\n".encode() + body


def read_message(proc: subprocess.Popen[bytes], timeout: float = 20.0) -> dict[str, Any] | None:
    deadline = time.time() + timeout
    headers = b""
    while time.time() < deadline:
        if not proc.stdout:
            return None
        ch = read_fd(proc.stdout.fileno(), 1, deadline)
        if not ch:
            return None
        headers += ch
        if headers.endswith(b"\r\n\r\n"):
            break
    else:
        return None
    length = 0
    for line in headers.split(b"\r\n"):
        if line.lower().startswith(b"content-length:"):
            length = int(line.split(b":", 1)[1].strip())
    if not proc.stdout or length <= 0:
        return None
    body = read_fd(proc.stdout.fileno(), length, deadline)
    if len(body) != length:
        return None
    return json.loads(body)


def read_fd(fd: int, length: int, deadline: float) -> bytes:
    chunks: list[bytes] = []
    remaining = length
    while remaining > 0 and time.time() < deadline:
        ready, _, _ = select.select([fd], [], [], max(0.1, deadline - time.time()))
        if not ready:
            break
        chunk = os.read(fd, remaining)
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def drain(proc: subprocess.Popen[bytes], req_id: int, timeout: float = 20.0) -> dict[str, Any]:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc.poll() is not None:
            err = read_stderr(proc)
            raise RuntimeError(f"server exited while waiting for response id {req_id}: {err}")
        msg = read_message(proc, timeout=max(0.1, deadline - time.time()))
        if msg is None:
            break
        if msg.get("id") == req_id:
            return msg
    raise RuntimeError(f"timed out waiting for response id {req_id}: {read_stderr(proc)}")


def read_stderr(proc: subprocess.Popen[bytes]) -> str:
    if not proc.stderr:
        return ""
    ready, _, _ = select.select([proc.stderr], [], [], 0)
    if not ready:
        return ""
    return proc.stderr.read().decode(errors="replace").strip()


def send(proc: subprocess.Popen[bytes], msg: dict[str, Any]) -> None:
    if not proc.stdin:
        raise RuntimeError("server stdin is closed")
    try:
        proc.stdin.write(encode(msg))
        proc.stdin.flush()
    except BrokenPipeError as exc:
        try:
            proc.stdin.close()
        except BrokenPipeError:
            pass
        raise RuntimeError(f"server stdin closed: {read_stderr(proc)}") from exc


def start_server(cmd: list[str], cwd: Path, env: dict[str, str] | None = None) -> subprocess.Popen[bytes]:
    return subprocess.Popen(
        cmd,
        cwd=cwd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )


def initialize(
    proc: subprocess.Popen[bytes],
    root: Path,
    req_id: int = 1,
    timeout: float = 20.0,
) -> dict[str, Any]:
    send(
        proc,
        {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": "initialize",
            "params": {
                "rootUri": uri(root),
                "capabilities": {
                    "textDocument": {
                        "completion": {},
                        "hover": {},
                        "definition": {},
                        "implementation": {},
                        "references": {},
                        "documentSymbol": {},
                        "signatureHelp": {},
                        "inlayHint": {},
                        "documentHighlight": {},
                        "foldingRange": {},
                        "selectionRange": {},
                        "semanticTokens": {"requests": {"full": True}},
                        "codeAction": {},
                        "rename": {},
                    },
                    "workspace": {"symbol": {}},
                },
            },
        },
    )
    response = drain(proc, req_id, timeout=timeout)
    send(proc, {"jsonrpc": "2.0", "method": "initialized", "params": {}})
    return response


def send_with_drain(
    proc: subprocess.Popen[bytes],
    msg: dict[str, Any],
    uris: set[str],
    diagnostics: dict[str, list[dict[str, Any]]],
) -> None:
    if not proc.stdin:
        raise RuntimeError("server stdin is closed")
    data = encode(msg)
    fd = proc.stdin.fileno()
    was_blocking = os.get_blocking(fd)
    os.set_blocking(fd, False)
    offset = 0
    try:
        while offset < len(data):
            if proc.poll() is not None:
                err = read_stderr(proc)
                raise RuntimeError(f"server exited while sending request: {err}")
            try:
                written = os.write(fd, data[offset : offset + 65536])
            except BlockingIOError:
                drain_available_diagnostics(proc, uris, diagnostics, quiet=0.01)
                select.select([], [fd], [], 0.05)
                continue
            if written <= 0:
                raise RuntimeError("server stdin stopped accepting bytes")
            offset += written
    except BrokenPipeError as exc:
        raise RuntimeError(f"server stdin closed: {read_stderr(proc)}") from exc
    finally:
        os.set_blocking(fd, was_blocking)


def did_open(
    proc: subprocess.Popen[bytes],
    path: Path,
    language_id: str = "fortran",
    drain_uris: set[str] | None = None,
    diagnostics: dict[str, list[dict[str, Any]]] | None = None,
) -> None:
    text = path.read_text(errors="replace")
    msg = {
        "jsonrpc": "2.0",
        "method": "textDocument/didOpen",
        "params": {
            "textDocument": {
                "uri": uri(path),
                "languageId": language_id,
                "version": 1,
                "text": text,
            }
        },
    }
    if drain_uris is not None and diagnostics is not None:
        send_with_drain(proc, msg, drain_uris, diagnostics)
    else:
        send(proc, msg)


def collect_diagnostics(
    proc: subprocess.Popen[bytes],
    uris: set[str],
    timeout: float = 2.0,
    quiet: float = 0.25,
    initial: dict[str, list[dict[str, Any]]] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    diagnostics: dict[str, list[dict[str, Any]]] = dict(initial or {})
    deadline = time.time() + timeout
    last_diagnostic_at: float | None = None
    while time.time() < deadline:
        if diagnostics.keys() >= uris and last_diagnostic_at is not None:
            remaining_quiet = quiet - (time.time() - last_diagnostic_at)
            if remaining_quiet <= 0:
                break
            read_timeout = min(max(0.1, remaining_quiet), deadline - time.time())
        else:
            read_timeout = max(0.1, deadline - time.time())
        if proc.poll() is not None:
            err = read_stderr(proc)
            raise RuntimeError(f"server exited while waiting for diagnostics: {err}")
        msg = read_message(proc, timeout=read_timeout)
        if msg is None:
            if diagnostics.keys() >= uris:
                break
            continue
        if msg.get("method") != "textDocument/publishDiagnostics":
            continue
        params = msg.get("params") or {}
        diag_uri = params.get("uri")
        if diag_uri in uris:
            diagnostics[diag_uri] = params.get("diagnostics") or []
            last_diagnostic_at = time.time()
    return diagnostics


def drain_available_diagnostics(
    proc: subprocess.Popen[bytes],
    uris: set[str],
    diagnostics: dict[str, list[dict[str, Any]]],
    quiet: float = 0.0,
) -> None:
    if not proc.stdout:
        return
    quiet_deadline = time.time() + quiet
    while True:
        timeout = max(0.0, quiet_deadline - time.time())
        ready, _, _ = select.select([proc.stdout], [], [], timeout)
        if not ready:
            return
        msg = read_message(proc, timeout=0.1)
        if msg is None:
            return
        quiet_deadline = time.time() + quiet
        if msg.get("method") != "textDocument/publishDiagnostics":
            continue
        params = msg.get("params") or {}
        diag_uri = params.get("uri")
        if diag_uri in uris:
            diagnostics[diag_uri] = params.get("diagnostics") or []


def request(
    proc: subprocess.Popen[bytes],
    req_id: int,
    method: str,
    params: dict[str, Any],
    timeout: float = 20.0,
) -> Any:
    send(proc, {"jsonrpc": "2.0", "id": req_id, "method": method, "params": params})
    response = drain(proc, req_id, timeout=timeout)
    if "error" in response:
        return {"error": response["error"]}
    return response.get("result")


def uri(path: Path) -> str:
    return path.resolve().as_uri()


def make_fixture(root: Path) -> dict[str, Path]:
    (root / "freight.toml").write_text(
        '[package]\nname = "fortran-lsp-fixture"\nversion = "0.1.0"\n\n'
        "[language.fortran]\nstandard = \"f2018\"\n"
    )
    files = {
        "math": root / "math.f90",
        "impl": root / "math_impl.f90",
        "app": root / "app.f90",
        "bad": root / "bad.f90",
        "actions": root / "actions.f90",
    }
    files["math"].write_text(MODULE_SOURCE)
    files["impl"].write_text(SUBMODULE_SOURCE)
    files["app"].write_text(APP_SOURCE)
    files["bad"].write_text(BAD_SOURCE)
    files["actions"].write_text(ACTION_SOURCE)
    return files


def copy_project_fixture(source: Path, root: Path, max_files: int = 0) -> dict[str, Path]:
    source = source.resolve()
    if not source.is_dir():
        raise RuntimeError(f"project fixture is not a directory: {source}")
    ignored = shutil.ignore_patterns(
        ".git",
        "target",
        ".freight",
        ".pkgs",
        "__pycache__",
        "build",
        "dist",
    )
    shutil.copytree(source, root, dirs_exist_ok=True, ignore=ignored)
    files = fortran_files(root)
    if max_files > 0:
        files = files[:max_files]
    if not files:
        raise RuntimeError(f"project fixture has no Fortran files: {source}")
    if not (root / "freight.toml").exists():
        (root / "freight.toml").write_text(
            '[package]\nname = "fortran-lsp-project-fixture"\nversion = "0.1.0"\n\n'
            "[language.fortran]\nstd = \"f2018\"\n"
        )
    return {relative_key(root, path): path for path in files}


def fortran_files(root: Path) -> list[Path]:
    exts = {".f", ".for", ".ftn", ".f77", ".f90", ".f95", ".f03", ".f08", ".f18"}
    return sorted(
        (
            path
            for path in root.rglob("*")
            if path.is_file() and path.suffix.lower() in exts
        ),
        key=lambda path: project_file_sort_key(root, path),
    )


def project_file_sort_key(root: Path, path: Path) -> tuple[int, str]:
    rel = path.resolve().relative_to(root.resolve()).as_posix()
    parts = rel.split("/")
    priority_names = {
        "include": 0,
        "inc": 0,
        "src": 1,
        "source": 1,
        "app": 2,
        "apps": 2,
        "example": 3,
        "examples": 3,
        "test": 4,
        "tests": 4,
    }
    priority = min((priority_names.get(part, 2) for part in parts[:-1]), default=2)
    return (priority, len(parts), rel)


def relative_key(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def write_python_shims(root: Path) -> Path:
    shim = root / "_py_shims"
    (shim / "packaging").mkdir(parents=True, exist_ok=True)
    (shim / "json5.py").write_text(
        "import json\n"
        "def load(fp, *args, **kwargs): return json.load(fp)\n"
        "def loads(s, *args, **kwargs): return json.loads(s)\n"
        "def dump(obj, fp, *args, **kwargs): return json.dump(obj, fp, *args, **kwargs)\n"
        "def dumps(obj, *args, **kwargs): return json.dumps(obj, *args, **kwargs)\n"
    )
    (shim / "packaging" / "__init__.py").write_text("from . import version\n")
    (shim / "packaging" / "version.py").write_text(
        "import re\n"
        "class Version:\n"
        "    def __init__(self, text):\n"
        "        self.text = str(text)\n"
        "        self.parts = tuple(int(p) for p in re.findall(r'\\d+', self.text)[:3])\n"
        "        self.is_prerelease = any(tag in self.text.lower() for tag in ['a', 'b', 'rc', 'dev'])\n"
        "    def __lt__(self, other): return self.parts < other.parts\n"
        "    def __gt__(self, other): return self.parts > other.parts\n"
        "    def __eq__(self, other): return self.parts == other.parts\n"
        "def parse(text): return Version(text)\n"
    )
    (shim / "setuptools_scm.py").write_text("def get_version(*args, **kwargs): return '0.0.0'\n")
    return shim


def normalize(value: Any, fixture: Path) -> Any:
    if isinstance(value, dict):
        return {k: normalize(v, fixture) for k, v in sorted(value.items()) if k not in {"data"}}
    if isinstance(value, list):
        return [normalize(v, fixture) for v in value]
    if isinstance(value, str):
        fixture_uri = uri(fixture)
        if value.startswith(fixture_uri):
            return value.replace(fixture_uri, "file://<fixture>", 1)
        return value.replace(str(fixture), "<fixture>")
    return value


def simplify_location(value: Any) -> Any:
    if isinstance(value, list):
        if not value:
            return None
        value = value[0]
    if not isinstance(value, dict):
        return value
    return {
        "uri": value.get("uri"),
        "range": value.get("range"),
    }


def simplify_location_line(value: Any) -> Any:
    loc = simplify_location(value)
    if not isinstance(loc, dict):
        return loc
    start = ((loc.get("range") or {}).get("start") or {})
    return {"uri": loc.get("uri"), "line": start.get("line")}


def simplify_reference_lines(value: Any, only_uri: str | None = None) -> Any:
    if value is None:
        return []
    if not isinstance(value, list):
        return value
    refs: set[tuple[str, int]] = set()
    for item in value:
        if not isinstance(item, dict):
            continue
        item_uri = item.get("uri")
        if not isinstance(item_uri, str):
            continue
        if only_uri is not None and item_uri != only_uri:
            continue
        start = ((item.get("range") or {}).get("start") or {})
        line = start.get("line")
        if isinstance(line, int):
            refs.add((item_uri, line))
    return [{"uri": item_uri, "line": line} for item_uri, line in sorted(refs)]


def simplify_rename_edit_lines(value: Any, only_uri: str, new_text: str) -> Any:
    if not isinstance(value, dict):
        return value
    edits: list[Any] = []
    changes = value.get("changes")
    if isinstance(changes, dict):
        edits.extend(changes.get(only_uri) or [])
    document_changes = value.get("documentChanges")
    if isinstance(document_changes, list):
        for change in document_changes:
            if not isinstance(change, dict):
                continue
            text_document = change.get("textDocument") or {}
            if text_document.get("uri") == only_uri:
                edits.extend(change.get("edits") or [])
    lines: set[int] = set()
    for edit in edits:
        if not isinstance(edit, dict) or edit.get("newText") != new_text:
            continue
        start = ((edit.get("range") or {}).get("start") or {})
        line = start.get("line")
        if isinstance(line, int):
            lines.add(line)
    return sorted(lines)


def simplify_folding_ranges(value: Any) -> Any:
    if value is None:
        return []
    if not isinstance(value, list):
        return value
    spans: set[tuple[int, int]] = set()
    for item in value:
        if not isinstance(item, dict):
            continue
        start = item.get("startLine")
        end = item.get("endLine")
        if isinstance(start, int) and isinstance(end, int) and end > start:
            spans.add((start, end))
    return [{"startLine": start, "endLine": end} for start, end in sorted(spans)]


def summarize_semantic_tokens(value: Any) -> Any:
    if not isinstance(value, dict):
        return value
    data = value.get("data")
    if not isinstance(data, list):
        return value
    token_count = len(data) // 5
    lines: set[int] = set()
    token_types: dict[int, int] = {}
    line = 0
    char = 0
    valid_tokens = 0
    for idx in range(0, len(data) - 4, 5):
        delta_line, delta_char, length, token_type, _mods = data[idx : idx + 5]
        if not all(isinstance(item, int) for item in [delta_line, delta_char, length, token_type]):
            continue
        line += delta_line
        char = char + delta_char if delta_line == 0 else delta_char
        if length <= 0:
            continue
        lines.add(line)
        token_types[token_type] = token_types.get(token_type, 0) + 1
        valid_tokens += 1
    return {
        "token_count": token_count,
        "valid_token_count": valid_tokens,
        "lines": sorted(lines),
        "token_types": {str(key): token_types[key] for key in sorted(token_types)},
    }


def method_not_found(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    error = value.get("error")
    return isinstance(error, dict) and error.get("code") == -32601


def simplify_signature(value: Any) -> Any:
    if not isinstance(value, dict):
        return value
    signatures = value.get("signatures") or []
    simplified: list[dict[str, Any]] = []
    for sig in signatures:
        if not isinstance(sig, dict):
            continue
        params = sig.get("parameters") or []
        simplified.append(
            {
                "label": sig.get("label"),
                "parameters": [
                    param.get("label") if isinstance(param, dict) else param for param in params
                ],
            }
        )
    return {
        "activeParameter": value.get("activeParameter"),
        "signatures": simplified,
    }


def simplify_project_signature(value: Any) -> Any:
    simplified = simplify_signature(value)
    if not isinstance(simplified, dict):
        return None
    signatures = simplified.get("signatures") or []
    out = []
    for sig in signatures:
        if not isinstance(sig, dict):
            continue
        label = sig.get("label")
        if not isinstance(label, str):
            continue
        params = sig.get("parameters") or []
        out.append(
            {
                "label": normalize_signature_text(label),
                "parameters": [
                    normalize_signature_text(param)
                    for param in params
                    if isinstance(param, str)
                ],
            }
        )
    return out


def normalize_signature_text(text: str) -> str:
    normalized = re.sub(r"\s+", " ", text).strip().lower()
    normalized = re.sub(r"^(?:module )?(?:subroutine|function) ", "", normalized)
    normalized = re.sub(r"\b([a-z_]\w*)=\1\b", r"\1", normalized)
    normalized = re.sub(r"\(\s+", "(", normalized)
    normalized = re.sub(r"\s+\)", ")", normalized)
    normalized = re.sub(r"\s+\(", "(", normalized)
    normalized = re.sub(r"\s*,\s*", ", ", normalized)
    return normalized


def simplify_hover_signature(value: Any) -> Any:
    if not isinstance(value, dict):
        return value
    contents = value.get("contents")
    if isinstance(contents, dict):
        text = contents.get("value", "")
    else:
        text = contents or ""
    match = re.search(
        r"\b(?:module\s+)?(?:subroutine|function)\s+([a-z_]\w*)\s*\(([^)]*)\)",
        text,
        flags=re.IGNORECASE,
    )
    if not match:
        return text
    args = ", ".join(part.strip() for part in match.group(2).split(",") if part.strip())
    return f"{match.group(1).lower()}({args})"


def hover_mentions_symbol(value: Any, symbol: str) -> bool:
    if not isinstance(value, dict):
        return False
    contents = value.get("contents")
    if isinstance(contents, dict):
        text = str(contents.get("value") or "")
    elif isinstance(contents, list):
        parts = []
        for item in contents:
            if isinstance(item, dict):
                parts.append(str(item.get("value") or ""))
            else:
                parts.append(str(item))
        text = "\n".join(parts)
    else:
        text = str(contents or "")
    pattern = re.compile(rf"\b{re.escape(symbol)}\b", flags=re.IGNORECASE)
    return bool(pattern.search(text))


def collect_document_symbols(items: Any, container: str | None = None) -> list[dict[str, Any]]:
    if not isinstance(items, list):
        return []
    out: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if isinstance(name, str):
            out.append(
                {
                    "name": name,
                    "containerName": item.get("containerName") or container,
                    "kind": item.get("kind"),
                }
            )
        out.extend(collect_document_symbols(item.get("children"), name if isinstance(name, str) else container))
    return out


def public_fixture_symbols(items: Any) -> list[str]:
    names = {"math", "axpy", "saxpy"}
    return sorted(
        {
            item["name"]
            for item in collect_document_symbols(items)
            if item.get("name") in names
        }
    )


def document_symbol_names(items: Any) -> list[str]:
    return sorted(
        {
            item["name"].lower()
            for item in collect_document_symbols(items)
            if isinstance(item.get("name"), str)
        }
    )


def simplify_workspace_symbols(items: Any) -> list[dict[str, Any]]:
    if not isinstance(items, list):
        return []
    out: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if not isinstance(name, str):
            continue
        short_name = name.rsplit("::", 1)[-1]
        container = item.get("containerName")
        if short_name not in {"axpy", "saxpy"}:
            continue
        out.append(
            {
                "name": short_name,
                "containerName": container,
                "kind": item.get("kind"),
            }
        )
    return sorted(out, key=lambda item: (str(item.get("containerName")), str(item.get("name")), str(item.get("kind"))))


def workspace_symbol_names(items: Any) -> list[str]:
    if not isinstance(items, list):
        return []
    names: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if isinstance(name, str):
            names.add(name.rsplit("::", 1)[-1].lower())
    return sorted(names)


def completion_labels(items: Any) -> list[str]:
    if isinstance(items, dict):
        items = items.get("items") or []
    if not isinstance(items, list):
        return []
    labels: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        label = item.get("label")
        if isinstance(label, str):
            labels.add(label.lower())
    return sorted(labels)


def completion_has_label(items: Any, label: str) -> bool:
    return label.lower() in completion_labels(items)


def diagnostic_messages(items: Any) -> list[str]:
    if not isinstance(items, list):
        return []
    messages: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        message = str(item.get("message", "")).strip().lower()
        message = re.sub(r"\s+", " ", message)
        message = re.sub(
            r"module [`\"]([^`\"]+)[`\"] could not be resolved",
            r"module \1 unresolved",
            message,
        )
        message = re.sub(
            r"module [`\"]([^`\"]+)[`\"] not found in project",
            r"module \1 unresolved",
            message,
        )
        if message:
            messages.add(message)
    return sorted(messages)


def project_module_names(files: dict[str, Path]) -> list[str]:
    modules: set[str] = set()
    module_re = re.compile(r"^\s*module\s+([a-z_]\w*)\b", flags=re.IGNORECASE)
    for path in files.values():
        for line in path.read_text(errors="replace").splitlines():
            match = module_re.match(line)
            if match and not line.lower().lstrip().startswith("module procedure"):
                modules.add(match.group(1).lower())
    return sorted(modules)


def project_declaration_files(root: Path, opened_files: dict[str, Path]) -> list[Path]:
    exts = {".f", ".for", ".ftn", ".f77", ".f90", ".f95", ".f03", ".f08", ".f18", ".fypp"}
    opened = {path.resolve() for path in opened_files.values()}
    paths = {
        path.resolve()
        for path in root.rglob("*")
        if path.is_file() and path.suffix.lower() in exts
    }
    paths.update(opened)
    return sorted(paths)


def logical_fortran_lines(text: str) -> list[str]:
    out: list[str] = []
    current = ""
    for raw_line in text.splitlines():
        line = strip_fortran_comment(raw_line).strip()
        if not line or line.startswith("#:"):
            continue
        continued = line.endswith("&")
        if continued:
            line = line[:-1].rstrip()
        if line.startswith("&"):
            line = line[1:].lstrip()
        current = f"{current} {line}".strip() if current else line
        if not continued:
            out.append(current)
            current = ""
    if current:
        out.append(current)
    return out


def strip_fortran_comment(line: str) -> str:
    quote: str | None = None
    idx = 0
    while idx < len(line):
        ch = line[idx]
        if quote is not None:
            if ch == quote:
                if idx + 1 < len(line) and line[idx + 1] == quote:
                    idx += 2
                    continue
                quote = None
        elif ch in {"'", '"'}:
            quote = ch
        elif ch == "!":
            return line[:idx]
        idx += 1
    return line


def split_fortran_names(text: str) -> list[str]:
    names: list[str] = []
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        part = part.split("=", 1)[0].strip()
        part = part.split("(", 1)[0].strip()
        match = re.match(r"([a-z_]\w*)\b", part, flags=re.IGNORECASE)
        if match:
            names.append(match.group(1).lower())
    return names


def project_declared_names(root: Path, opened_files: dict[str, Path]) -> list[str]:
    names: set[str] = set()
    declaration_re = re.compile(
        r"^\s*(?:integer|real|complex|logical|character|type\s*\([^)]*\)|class\s*\([^)]*\))\b.*::\s*(.+)$",
        flags=re.IGNORECASE,
    )
    procedure_re = re.compile(
        r"^\s*(?:module\s+)?(?:subroutine|function)\s+([a-z_]\w*)\b",
        flags=re.IGNORECASE,
    )
    type_re = re.compile(r"^\s*type\s*(?:,\s*[^:]*)?::\s*([a-z_]\w*)\b", flags=re.IGNORECASE)
    public_re = re.compile(r"^\s*public\s*::\s*(.+)$", flags=re.IGNORECASE)
    use_alias_re = re.compile(r"\b([a-z_]\w*)\s*=>\s*[a-z_]\w*\b", flags=re.IGNORECASE)
    for path in project_declaration_files(root, opened_files):
        try:
            lines = logical_fortran_lines(path.read_text(errors="replace"))
        except OSError:
            continue
        for line in lines:
            lowered = line.lower().lstrip()
            if lowered.startswith("module procedure"):
                continue
            match = declaration_re.match(line)
            if match:
                names.update(split_fortran_names(match.group(1)))
                continue
            match = procedure_re.match(line)
            if match:
                names.add(match.group(1).lower())
                continue
            match = type_re.match(line)
            if match:
                names.add(match.group(1).lower())
                continue
            match = public_re.match(line)
            if match:
                names.update(split_fortran_names(match.group(1)))
                continue
            if line.lower().lstrip().startswith("use ") and "=>" in line:
                names.update(match.group(1).lower() for match in use_alias_re.finditer(line))
    return sorted(names)


def project_conditional_include_templates(opened_files: dict[str, Path]) -> list[str]:
    templates: list[str] = []
    for name, path in opened_files.items():
        try:
            source = path.read_text(errors="replace").lower()
        except OSError:
            continue
        if "#ifndef mod_include" in source and "#endif" in source:
            templates.append(name)
    return templates


def project_definition_probe_points(files: dict[str, Path], limit: int = 20) -> list[dict[str, Any]]:
    patterns = [
        re.compile(r"^\s*module\s+(?!procedure\b)([a-z_]\w*)\b", flags=re.IGNORECASE),
        re.compile(r"^\s*(?:module\s+)?subroutine\s+([a-z_]\w*)\b", flags=re.IGNORECASE),
        re.compile(r"^\s*(?:[a-z_]\w*(?:\s*\([^)]*\))?\s+)?(?:module\s+)?function\s+([a-z_]\w*)\b", flags=re.IGNORECASE),
        re.compile(r"^\s*type\s*(?:,\s*[^:]*)?::\s*([a-z_]\w*)\b", flags=re.IGNORECASE),
    ]
    points: list[dict[str, Any]] = []
    for file_name, path in sorted(files.items()):
        if file_name.startswith("archive/src/demos/") and file_name.endswith(".f"):
            continue
        try:
            lines = path.read_text(errors="replace").splitlines()
        except OSError:
            continue
        for line_no, raw_line in enumerate(lines):
            line = strip_fortran_comment(raw_line)
            if line.lower().lstrip().startswith("end "):
                continue
            for pattern in patterns:
                match = pattern.match(line)
                if not match:
                    continue
                symbol = match.group(1)
                char = raw_line.lower().find(symbol.lower())
                if char >= 0:
                    points.append(
                        {
                            "file": file_name,
                            "symbol": symbol.lower(),
                            "line": line_no,
                            "character": char,
                        }
                    )
                break
            if len(points) >= limit:
                return points
    return points


def project_reference_probe_points(files: dict[str, Path], limit: int = 20) -> list[dict[str, Any]]:
    free_form_files = {
        name: path
        for name, path in files.items()
        if path.suffix.lower() not in {".f", ".for", ".ftn", ".f77"}
    }
    return project_definition_probe_points(free_form_files, limit=limit)


def project_implementation_probe_points(files: dict[str, Path], limit: int = 20) -> list[dict[str, Any]]:
    patterns = [
        re.compile(
            r"^\s*(?:pure\s+|elemental\s+|recursive\s+)*module\s+subroutine\s+([a-z_]\w*)\b",
            flags=re.IGNORECASE,
        ),
        re.compile(
            r"^\s*(?:pure\s+|elemental\s+|recursive\s+)*(?:[a-z_]\w*(?:\s*\([^)]*\))?\s+)?module\s+function\s+([a-z_]\w*)\b",
            flags=re.IGNORECASE,
        ),
    ]
    points: list[dict[str, Any]] = []
    for file_name, path in sorted(files.items()):
        if file_name.startswith("archive/src/demos/") and file_name.endswith(".f"):
            continue
        try:
            lines = path.read_text(errors="replace").splitlines()
        except OSError:
            continue
        if any(
            re.match(r"^\s*submodule\s*\(", strip_fortran_comment(line), flags=re.IGNORECASE)
            for line in lines
        ):
            continue
        for line_no, raw_line in enumerate(lines):
            line = strip_fortran_comment(raw_line)
            if line.lower().lstrip().startswith("end "):
                continue
            for pattern in patterns:
                match = pattern.match(line)
                if not match:
                    continue
                symbol = match.group(1)
                char = raw_line.lower().find(symbol.lower())
                if char >= 0:
                    points.append(
                        {
                            "file": file_name,
                            "symbol": symbol.lower(),
                            "line": line_no,
                            "character": char,
                        }
                    )
                break
            if len(points) >= limit:
                return points
    return points


def project_signature_probe_points(files: dict[str, Path], limit: int = 20) -> list[dict[str, Any]]:
    call_re = re.compile(r"\bcall\s+([a-z_]\w*)\s*\(", flags=re.IGNORECASE)
    procedure_dummy_re = re.compile(
        r"^\s*procedure\s*\([^)]*\)\s*(?:,\s*[^:]*)?::\s*(.+)$",
        flags=re.IGNORECASE,
    )
    points: list[dict[str, Any]] = []
    for file_name, path in sorted(files.items()):
        if file_name.startswith("archive/src/demos/") and file_name.endswith(".f"):
            continue
        try:
            lines = path.read_text(errors="replace").splitlines()
        except OSError:
            continue
        procedure_dummies: set[str] = set()
        for raw_line in lines:
            match = procedure_dummy_re.match(strip_fortran_comment(raw_line))
            if match:
                procedure_dummies.update(split_fortran_names(match.group(1)))
        fixed_form = path.suffix.lower() in {".f", ".for", ".ftn", ".f77"}
        for line_no, raw_line in enumerate(lines):
            if fixed_form and raw_line[:1] in {"c", "C", "*", "!"}:
                continue
            line = strip_fortran_comment(raw_line)
            for match in call_re.finditer(line):
                call_name = match.group(1).lower()
                if call_name in procedure_dummies:
                    continue
                open_paren = raw_line.find("(", match.start())
                if open_paren < 0:
                    continue
                points.append(
                    {
                        "file": file_name,
                        "symbol": call_name,
                        "line": line_no,
                        "character": open_paren + 1,
                    }
                )
                break
            if len(points) >= limit:
                return points
    return points


def project_completion_probe_points(files: dict[str, Path], limit: int = 20) -> list[dict[str, Any]]:
    call_re = re.compile(r"\bcall\s+([a-z_]\w*)\s*(?:\(|$)", flags=re.IGNORECASE)
    points: list[dict[str, Any]] = []
    for file_name, path in sorted(files.items()):
        if file_name.startswith("archive/src/demos/") and file_name.endswith(".f"):
            continue
        if path.suffix.lower() in {".f", ".for", ".ftn", ".f77"}:
            continue
        try:
            lines = path.read_text(errors="replace").splitlines()
        except OSError:
            continue
        for line_no, raw_line in enumerate(lines):
            line = strip_fortran_comment(raw_line)
            for match in call_re.finditer(line):
                call_name = match.group(1).lower()
                if len(call_name) < 3:
                    continue
                char = raw_line.lower().find(call_name[:3], match.start())
                if char < 0:
                    continue
                points.append(
                    {
                        "file": file_name,
                        "symbol": call_name,
                        "line": line_no,
                        "character": char + 3,
                    }
                )
                break
            if len(points) >= limit:
                return points
    return points


def project_rename_probe_points(files: dict[str, Path], limit: int = 20) -> list[dict[str, Any]]:
    declaration_re = re.compile(
        r"^\s*(?:integer|real|complex|logical|character|type\s*\([^)]*\)|class\s*\([^)]*\))\b.*::\s*(.+)$",
        flags=re.IGNORECASE,
    )
    points: list[dict[str, Any]] = []
    for file_name, path in sorted(files.items()):
        if file_name.startswith("archive/src/demos/") and file_name.endswith(".f"):
            continue
        if path.suffix.lower() in {".f", ".for", ".ftn", ".f77"}:
            continue
        try:
            lines = path.read_text(errors="replace").splitlines()
        except OSError:
            continue
        searchable_source = "\n".join(strip_fortran_comment(line) for line in lines)
        for line_no, raw_line in enumerate(lines):
            line = strip_fortran_comment(raw_line)
            match = declaration_re.match(line)
            if not match:
                continue
            rhs_start = raw_line.find("::")
            if rhs_start < 0:
                continue
            rhs_start += 2
            for name in split_fortran_names(match.group(1)):
                if len(name) < 3:
                    continue
                if re.search(rf"\brenamed_{re.escape(name)}\b", searchable_source, re.IGNORECASE):
                    continue
                occurrences = list(
                    re.finditer(rf"\b{re.escape(name)}\b", searchable_source, re.IGNORECASE)
                )
                if len(occurrences) < 2:
                    continue
                name_match = re.search(rf"\b{re.escape(name)}\b", raw_line[rhs_start:], re.IGNORECASE)
                if not name_match:
                    continue
                points.append(
                    {
                        "file": file_name,
                        "symbol": name,
                        "line": line_no,
                        "character": rhs_start + name_match.start(),
                        "new_name": f"renamed_{name}",
                    }
                )
                break
            if len(points) >= limit:
                return points
    return points


def project_folding_probe_files(files: dict[str, Path], limit: int = 20) -> list[str]:
    selected: list[str] = []
    patterns = [
        re.compile(r"^\s*module\s+(?!procedure\b)", flags=re.IGNORECASE),
        re.compile(r"^\s*submodule\s*\(", flags=re.IGNORECASE),
        re.compile(r"^\s*(?:abstract\s+)?interface\b", flags=re.IGNORECASE),
        re.compile(r"^\s*(?:subroutine|function)\s+", flags=re.IGNORECASE),
    ]
    for file_name, path in sorted(files.items()):
        if file_name.startswith("archive/src/demos/") and file_name.endswith(".f"):
            continue
        try:
            lines = path.read_text(errors="replace").splitlines()
        except OSError:
            continue
        fixed_form = path.suffix.lower() in {".f", ".for", ".ftn", ".f77"}
        has_fixed_continuation = fixed_form and any(
            len(line) > 5 and line[:1] not in {"c", "C", "*", "!"} and line[5:6].strip()
            for line in lines
        )
        has_foldable_scope = any(
            any(pattern.match(strip_fortran_comment(line)) for pattern in patterns)
            for line in lines
        )
        if has_foldable_scope or has_fixed_continuation:
            selected.append(file_name)
        if len(selected) >= limit:
            return selected
    return selected


def project_semantic_probe_files(files: dict[str, Path], limit: int = 12) -> list[str]:
    candidates: list[tuple[int, int, str]] = []
    fallback: list[tuple[int, int, str]] = []
    patterns = [
        re.compile(r"^\s*#\s*(?:define|ifdef|ifndef|if|elif)\b", flags=re.IGNORECASE),
        re.compile(r"^\s*(?:module|submodule)\b", flags=re.IGNORECASE),
        re.compile(r"^\s*type\s*(?:,|\b)", flags=re.IGNORECASE),
        re.compile(r"^\s*procedure\s*(?:\(|::)", flags=re.IGNORECASE),
        re.compile(r"^\s*(?:subroutine|function)\s+", flags=re.IGNORECASE),
        re.compile(r"\bclass\s*\(", flags=re.IGNORECASE),
        re.compile(r"\buse\s+[a-z_]\w*", flags=re.IGNORECASE),
    ]
    for file_name, path in sorted(files.items()):
        if file_name.startswith("archive/src/demos/") and file_name.endswith(".f"):
            continue
        try:
            lines = path.read_text(errors="replace").splitlines()
        except OSError:
            continue
        line_count = len(lines)
        fixed_form = path.suffix.lower() in {".f", ".for", ".ftn", ".f77"}
        has_fixed_continuation = fixed_form and any(
            len(line) > 5 and line[:1] not in {"c", "C", "*", "!"} and line[5:6].strip()
            for line in lines
        )
        has_semantic_shape = any(
            any(pattern.search(strip_fortran_comment(line)) for pattern in patterns)
            for line in lines
        )
        if has_semantic_shape or has_fixed_continuation:
            ext_priority = 1 if fixed_form else 0
            item = (ext_priority, line_count, file_name)
            if line_count <= 1_200:
                candidates.append(item)
            else:
                fallback.append(item)
    selected = [file_name for _priority, _lines, file_name in sorted(candidates)[:limit]]
    if len(selected) < limit:
        selected.extend(
            file_name
            for _priority, _lines, file_name in sorted(fallback)[: limit - len(selected)]
        )
    return selected


def has_math_prototype_reference(items: Any) -> bool:
    if not isinstance(items, list):
        return False
    for item in items:
        if not isinstance(item, dict):
            continue
        if not str(item.get("uri", "")).endswith("/math.f90"):
            continue
        range_ = item.get("range") or {}
        start = range_.get("start") or {}
        if start.get("line") == 2:
            return True
    return False


def has_unresolved_module_diagnostic(items: Any) -> bool:
    if not isinstance(items, list):
        return False
    for item in items:
        if not isinstance(item, dict):
            continue
        message = str(item.get("message", "")).lower()
        if "missing_mod" in message and (
            "not found" in message
            or "not resolved" in message
            or "could not be resolved" in message
            or "could not be found" in message
        ):
            return True
    return False


def comparable_result(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "hover_call_signature": simplify_hover_signature(raw.get("hover_call")),
        "definition_call": simplify_location(raw.get("definition_call")),
        "references_call_has_prototype": has_math_prototype_reference(raw.get("references_call")),
        "signature_call": simplify_signature(raw.get("signature_call")),
        "completion_call_has_axpy": "axpy" in completion_labels(raw.get("completion_call")),
        "document_symbols": public_fixture_symbols(raw.get("document_symbols")),
        "implementation_proto": simplify_location(raw.get("implementation_proto")),
        "diagnostics_bad_has_unresolved_module": has_unresolved_module_diagnostic(
            raw.get("diagnostics_bad")
        ),
    }


def known_divergences(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "definition_impl": simplify_location(raw.get("definition_impl")),
        "workspace_symbol": simplify_workspace_symbols(raw.get("workspace_symbol")),
    }


def assert_freight_native_extras(raw: dict[str, Any]) -> None:
    inlay = raw.get("native_inlay")
    if not isinstance(inlay, list) or not any(
        isinstance(item, dict) and item.get("label") == "a:" for item in inlay
    ):
        raise RuntimeError("native Freight inlayHint did not return an `a:` argument hint")

    highlights = raw.get("native_highlights")
    if not isinstance(highlights, list) or len(highlights) < 2:
        raise RuntimeError("native Freight documentHighlight did not return local references")

    folds = raw.get("native_folds")
    if not isinstance(folds, list) or not any(
        isinstance(item, dict) and item.get("startLine") == 0 and item.get("endLine", 0) >= 6
        for item in folds
    ):
        raise RuntimeError("native Freight foldingRange did not return a module fold")

    selection = raw.get("native_selection")
    if not isinstance(selection, list) or not selection or not isinstance(selection[0], dict):
        raise RuntimeError("native Freight selectionRange did not return a range chain")
    if "parent" not in selection[0]:
        raise RuntimeError("native Freight selectionRange did not include an enclosing parent")

    semantic = raw.get("native_semantic")
    data = semantic.get("data") if isinstance(semantic, dict) else None
    if not isinstance(data, list) or len(data) < 5 or len(data) % 5 != 0:
        raise RuntimeError("native Freight semanticTokens/full did not return encoded token data")

    rename = raw.get("native_rename")
    changes = rename.get("changes") if isinstance(rename, dict) else None
    if not isinstance(changes, dict) or not any(
        isinstance(edits, list)
        and any(isinstance(edit, dict) and edit.get("newText") == "saxpy" for edit in edits)
        for edits in changes.values()
    ):
        raise RuntimeError("native Freight rename did not return workspace edits")

    actions = raw.get("native_code_actions")
    if not isinstance(actions, list) or not any(
        isinstance(item, dict)
        and item.get("kind") == "quickfix"
        and "deferred" in str(item.get("title", "")).lower()
        for item in actions
    ):
        raise RuntimeError("native Freight codeAction did not return deferred-procedure quickfix")


def run_suite(
    proc: subprocess.Popen[bytes],
    root: Path,
    files: dict[str, Path],
    request_timeout: float,
    diagnostic_timeout: float,
    diagnostic_quiet: float,
    settle_delay: float,
    freight_native_extras: bool = False,
) -> dict[str, Any]:
    initialize(proc, root, timeout=request_timeout)
    diagnostic_uris = {uri(files["bad"])}
    diagnostics: dict[str, list[dict[str, Any]]] = {}
    for name, path in files.items():
        did_open(proc, path)
        drain_available_diagnostics(proc, diagnostic_uris, diagnostics, quiet=0.03)
    diagnostics = collect_diagnostics(
        proc,
        diagnostic_uris,
        timeout=diagnostic_timeout,
        quiet=diagnostic_quiet,
        initial=diagnostics,
    )
    time.sleep(settle_delay)

    app_doc = {"textDocument": {"uri": uri(files["app"])}}
    math_doc = {"textDocument": {"uri": uri(files["math"])}}
    impl_doc = {"textDocument": {"uri": uri(files["impl"])}}
    actions_doc = {"textDocument": {"uri": uri(files["actions"])}}
    reqs = [
        ("hover_call", "textDocument/hover", {**app_doc, "position": {"line": 3, "character": 6}}),
        ("definition_call", "textDocument/definition", {**app_doc, "position": {"line": 3, "character": 6}}),
        ("references_call", "textDocument/references", {**app_doc, "position": {"line": 3, "character": 6}, "context": {"includeDeclaration": True}}),
        ("signature_call", "textDocument/signatureHelp", {**app_doc, "position": {"line": 3, "character": 10}}),
        ("completion_call", "textDocument/completion", {**app_doc, "position": {"line": 3, "character": 6}}),
        ("document_symbols", "textDocument/documentSymbol", math_doc),
        ("implementation_proto", "textDocument/implementation", {**math_doc, "position": {"line": 2, "character": 18}}),
        ("definition_impl", "textDocument/definition", {**impl_doc, "position": {"line": 2, "character": 18}}),
        ("workspace_symbol", "workspace/symbol", {"query": "ax"}),
    ]
    out: dict[str, Any] = {}
    for idx, (name, method, params) in enumerate(reqs, start=10):
        out[name] = request(proc, idx, method, params, timeout=request_timeout)
    if freight_native_extras:
        extra_reqs = [
            (
                "native_inlay",
                "textDocument/inlayHint",
                {
                    **app_doc,
                    "range": {
                        "start": {"line": 3, "character": 0},
                        "end": {"line": 3, "character": 24},
                    },
                },
            ),
            (
                "native_highlights",
                "textDocument/documentHighlight",
                {**app_doc, "position": {"line": 3, "character": 6}},
            ),
            ("native_folds", "textDocument/foldingRange", math_doc),
            (
                "native_selection",
                "textDocument/selectionRange",
                {**app_doc, "positions": [{"line": 3, "character": 6}]},
            ),
            ("native_semantic", "textDocument/semanticTokens/full", math_doc),
            (
                "native_rename",
                "textDocument/rename",
                {**app_doc, "position": {"line": 3, "character": 6}, "newName": "saxpy"},
            ),
            ("native_code_actions", "textDocument/codeAction", actions_doc),
        ]
        for idx, (name, method, params) in enumerate(extra_reqs, start=1_000):
            out[name] = request(proc, idx, method, params, timeout=request_timeout)
        assert_freight_native_extras(out)
    out["diagnostics_bad"] = diagnostics.get(uri(files["bad"]), [])
    return normalize(
        {
            "comparable": comparable_result(out),
            "known_divergences": known_divergences(out),
        },
        root,
    )


def run_project_suite(
    proc: subprocess.Popen[bytes],
    label: str,
    root: Path,
    files: dict[str, Path],
    request_timeout: float,
    diagnostic_timeout: float,
    diagnostic_quiet: float,
    settle_delay: float,
    verbose: bool = False,
) -> dict[str, Any]:
    def progress(message: str) -> None:
        if verbose:
            print(f"[{label}] {message}", file=sys.stderr, flush=True)

    progress("initialize")
    initialize(proc, root, timeout=request_timeout)
    diagnostic_uris = {uri(path) for path in files.values()}
    diagnostics: dict[str, list[dict[str, Any]]] = {}
    progress(f"open {len(files)} files")
    for name, path in files.items():
        progress(f"open {name}")
        did_open(proc, path, drain_uris=diagnostic_uris, diagnostics=diagnostics)
        progress(f"opened {name}")
        drain_available_diagnostics(proc, diagnostic_uris, diagnostics, quiet=0.03)
    progress("collect diagnostics")
    diagnostics = collect_diagnostics(
        proc,
        diagnostic_uris,
        timeout=diagnostic_timeout,
        quiet=diagnostic_quiet,
        initial=diagnostics,
    )
    time.sleep(settle_delay)

    document_symbols: dict[str, Any] = {}
    for idx, (name, path) in enumerate(files.items(), start=100):
        progress(f"documentSymbol {name}")
        document_symbols[name] = request(
            proc,
            idx,
            "textDocument/documentSymbol",
            {"textDocument": {"uri": uri(path)}},
            timeout=request_timeout,
        )
    definition_probes: dict[str, Any] = {}
    probe_points = project_definition_probe_points(files)
    for offset, point in enumerate(probe_points, start=1):
        progress(f"definition probe {point['file']}:{point['line']}:{point['symbol']}")
        probe = request(
            proc,
            5_000 + offset,
            "textDocument/definition",
            {
                "textDocument": {"uri": uri(files[point["file"]])},
                "position": {"line": point["line"], "character": point["character"]},
            },
            timeout=request_timeout,
        )
        key = f"{point['file']}:{point['line']}:{point['symbol']}"
        definition_probes[key] = simplify_location_line(probe)
    hover_probes: dict[str, Any] = {}
    for offset, point in enumerate(probe_points, start=1):
        progress(f"hover probe {point['file']}:{point['line']}:{point['symbol']}")
        probe = request(
            proc,
            6_000 + offset,
            "textDocument/hover",
            {
                "textDocument": {"uri": uri(files[point["file"]])},
                "position": {"line": point["line"], "character": point["character"]},
            },
            timeout=request_timeout,
        )
        key = f"{point['file']}:{point['line']}:{point['symbol']}"
        hover_probes[key] = hover_mentions_symbol(probe, point["symbol"])
    reference_probes: dict[str, Any] = {}
    for offset, point in enumerate(project_reference_probe_points(files), start=1):
        progress(f"references probe {point['file']}:{point['line']}:{point['symbol']}")
        probe_uri = uri(files[point["file"]])
        probe = request(
            proc,
            7_000 + offset,
            "textDocument/references",
            {
                "textDocument": {"uri": probe_uri},
                "position": {"line": point["line"], "character": point["character"]},
                "context": {"includeDeclaration": True},
            },
            timeout=request_timeout,
        )
        key = f"{point['file']}:{point['line']}:{point['symbol']}"
        reference_probes[key] = simplify_reference_lines(probe, only_uri=probe_uri)
    implementation_probes: dict[str, Any] = {}
    for offset, point in enumerate(project_implementation_probe_points(files), start=1):
        progress(f"implementation probe {point['file']}:{point['line']}:{point['symbol']}")
        probe = request(
            proc,
            11_000 + offset,
            "textDocument/implementation",
            {
                "textDocument": {"uri": uri(files[point["file"]])},
                "position": {"line": point["line"], "character": point["character"]},
            },
            timeout=request_timeout,
        )
        key = f"{point['file']}:{point['line']}:{point['symbol']}"
        implementation_probes[key] = simplify_location_line(probe)
    signature_probes: dict[str, Any] = {}
    for offset, point in enumerate(project_signature_probe_points(files), start=1):
        progress(f"signature probe {point['file']}:{point['line']}:{point['symbol']}")
        probe = request(
            proc,
            8_000 + offset,
            "textDocument/signatureHelp",
            {
                "textDocument": {"uri": uri(files[point["file"]])},
                "position": {"line": point["line"], "character": point["character"]},
            },
            timeout=request_timeout,
        )
        key = f"{point['file']}:{point['line']}:{point['symbol']}"
        signature_probes[key] = simplify_project_signature(probe)
    completion_probes: dict[str, Any] = {}
    for offset, point in enumerate(project_completion_probe_points(files), start=1):
        progress(f"completion probe {point['file']}:{point['line']}:{point['symbol']}")
        probe = request(
            proc,
            9_000 + offset,
            "textDocument/completion",
            {
                "textDocument": {"uri": uri(files[point["file"]])},
                "position": {"line": point["line"], "character": point["character"]},
            },
            timeout=request_timeout,
        )
        key = f"{point['file']}:{point['line']}:{point['symbol']}"
        completion_probes[key] = completion_has_label(probe, point["symbol"])
    rename_probes: dict[str, Any] = {}
    for offset, point in enumerate(project_rename_probe_points(files), start=1):
        progress(f"rename probe {point['file']}:{point['line']}:{point['symbol']}")
        probe_uri = uri(files[point["file"]])
        probe = request(
            proc,
            12_000 + offset,
            "textDocument/rename",
            {
                "textDocument": {"uri": probe_uri},
                "position": {"line": point["line"], "character": point["character"]},
                "newName": point["new_name"],
            },
            timeout=request_timeout,
        )
        key = f"{point['file']}:{point['line']}:{point['symbol']}"
        rename_probes[key] = simplify_rename_edit_lines(probe, probe_uri, point["new_name"])
    folding_probes: dict[str, Any] = {}
    for offset, file_name in enumerate(project_folding_probe_files(files), start=1):
        progress(f"folding probe {file_name}")
        probe = request(
            proc,
            13_000 + offset,
            "textDocument/foldingRange",
            {"textDocument": {"uri": uri(files[file_name])}},
            timeout=request_timeout,
        )
        folding_probes[file_name] = simplify_folding_ranges(probe)
    semantic_probes: dict[str, Any] = {}
    for offset, file_name in enumerate(project_semantic_probe_files(files), start=1):
        progress(f"semantic probe {file_name}")
        probe = request(
            proc,
            14_000 + offset,
            "textDocument/semanticTokens/full",
            {"textDocument": {"uri": uri(files[file_name])}},
            timeout=request_timeout,
        )
        semantic_probes[file_name] = summarize_semantic_tokens(probe)
    progress("workspace/symbol")
    workspace_symbols = request(
        proc,
        10_000,
        "workspace/symbol",
        {"query": ""},
        timeout=request_timeout,
    )

    out = {
        "diagnostics": {
            name: diagnostic_messages(diagnostics.get(uri(path), []))
            for name, path in files.items()
        },
        "document_symbols": {
            name: document_symbol_names(document_symbols.get(name))
            for name in files
        },
        "workspace_symbols": workspace_symbol_names(workspace_symbols),
        "definition_probes": definition_probes,
        "hover_probes": hover_probes,
        "reference_probes": reference_probes,
        "implementation_probes": implementation_probes,
        "signature_probes": signature_probes,
        "completion_probes": completion_probes,
        "rename_probes": rename_probes,
        "folding_probes": folding_probes,
        "semantic_probes": semantic_probes,
        "project_modules": project_module_names(files),
        "project_declared_names": project_declared_names(root, files),
        "conditional_include_templates": project_conditional_include_templates(files),
    }
    return normalize(out, root)


def diff_json(left: Any, right: Any) -> str:
    lhs = json.dumps(left, indent=2, sort_keys=True).splitlines()
    rhs = json.dumps(right, indent=2, sort_keys=True).splitlines()
    return "\n".join(difflib.unified_diff(lhs, rhs, fromfile="freight", tofile="fortls", lineterm=""))


def remove_known_project_module_diagnostics(
    diagnostics: dict[str, list[str]],
    module_names: set[str],
    symbol_names: set[str],
    conditional_include_templates: set[str],
) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    unresolved_re = re.compile(r"^module ([a-z_]\w*) unresolved$", flags=re.IGNORECASE)
    missing_object_re = re.compile(r'^object "([^"]+)" not found in scope$', flags=re.IGNORECASE)
    missing_parent_type_re = re.compile(
        r"^parent type `([^`]+)` for `[^`]+` could not be resolved$",
        flags=re.IGNORECASE,
    )
    missing_ancestor_prototype_re = re.compile(
        r"^module procedure `([^`]+)` has no matching ancestor interface prototype$",
        flags=re.IGNORECASE,
    )
    json_fortran_mask_noise = {
        "test/jf_test_07.F90": {"variable \"root\" masks variable in parent scope"},
        "test/jf_test_08.F90": {"variable \"newline\" masks variable in parent scope"},
        "test/jf_test_12.F90": {"variable \"root\" masks variable in parent scope"},
        "test/jf_test_20.F90": {"variable \"root\" masks variable in parent scope"},
    }
    for name, messages in diagnostics.items():
        odepack_legacy_demo_noise = name.startswith("archive/src/demos/") and name.endswith(".f")
        kept = []
        for message in messages:
            if odepack_legacy_demo_noise and (
                message == "subroutine/function definition before contains statement"
                or message == "unexpected end statement: no open scopes"
                or re.match(
                    r'^variable "[^"]+" (masks variable in parent scope|declared twice in scope)$',
                    message,
                    flags=re.IGNORECASE,
                )
            ):
                continue
            if name == "archive/src/opkdmain.f" and message == "module lsode unresolved":
                continue
            if name == "src/json_value_module.F90" and message.startswith(
                "no matching declaration found for argument "
            ):
                continue
            if message in json_fortran_mask_noise.get(name, set()):
                continue
            if name in conditional_include_templates and (
                message
                in {
                    "implicit statement without enclosing scope",
                    "visibility statement without enclosing scope",
                }
                or re.match(
                    r'^variable "[^"]+" masks variable in parent scope$',
                    message,
                    flags=re.IGNORECASE,
                )
            ):
                continue
            match = unresolved_re.match(message)
            if match and match.group(1).lower() in module_names:
                continue
            match = missing_object_re.match(message)
            if match and match.group(1).lower() in symbol_names:
                continue
            match = missing_parent_type_re.match(message)
            if match and match.group(1).lower() in symbol_names:
                continue
            match = missing_ancestor_prototype_re.match(message)
            if match and match.group(1).lower() in symbol_names:
                continue
            kept.append(message)
        out[name] = kept
    return out


def project_diff(freight_result: dict[str, Any], fortls_result: dict[str, Any]) -> str:
    diffs: list[str] = []
    project_modules = set(freight_result.get("project_modules") or []) | set(
        fortls_result.get("project_modules") or []
    )
    project_symbols = {
        symbol
        for result in [freight_result, fortls_result]
        for symbols in result["document_symbols"].values()
        for symbol in symbols
    }
    project_symbols.update(freight_result.get("project_declared_names") or [])
    project_symbols.update(fortls_result.get("project_declared_names") or [])
    conditional_include_templates = set(
        freight_result.get("conditional_include_templates") or []
    ) | set(fortls_result.get("conditional_include_templates") or [])
    freight_diagnostics = remove_known_project_module_diagnostics(
        freight_result["diagnostics"],
        project_modules,
        project_symbols,
        conditional_include_templates,
    )
    fortls_diagnostics = remove_known_project_module_diagnostics(
        fortls_result["diagnostics"],
        project_modules,
        project_symbols,
        conditional_include_templates,
    )
    if freight_diagnostics != fortls_diagnostics:
        diffs.append("diagnostics differ:")
        diffs.append(diff_json(freight_diagnostics, fortls_diagnostics))

    missing_document_symbols: dict[str, list[str]] = {}
    for name, fortls_symbols in fortls_result["document_symbols"].items():
        freight_symbols = set(freight_result["document_symbols"].get(name, []))
        missing = sorted(set(fortls_symbols) - freight_symbols)
        if missing:
            missing_document_symbols[name] = missing
    if missing_document_symbols:
        diffs.append("document symbols missing from Freight:")
        diffs.append(json.dumps(missing_document_symbols, indent=2, sort_keys=True))

    fortls_document_names = {
        symbol
        for symbols in fortls_result["document_symbols"].values()
        for symbol in symbols
    }
    fortls_workspace = {
        name
        for name in fortls_result["workspace_symbols"]
        if isinstance(name, str) and not name.startswith("#")
        and name in fortls_document_names
    }
    freight_workspace = set(freight_result["workspace_symbols"])
    missing_workspace = sorted(fortls_workspace - freight_workspace)
    if missing_workspace:
        diffs.append("workspace symbols missing from Freight:")
        diffs.append(json.dumps(missing_workspace, indent=2, sort_keys=True))

    if freight_result.get("definition_probes") != fortls_result.get("definition_probes"):
        diffs.append("definition probes differ:")
        diffs.append(
            diff_json(
                freight_result.get("definition_probes") or {},
                fortls_result.get("definition_probes") or {},
            )
        )
    if freight_result.get("hover_probes") != fortls_result.get("hover_probes"):
        diffs.append("hover probes differ:")
        diffs.append(
            diff_json(
                freight_result.get("hover_probes") or {},
                fortls_result.get("hover_probes") or {},
            )
        )
    if freight_result.get("reference_probes") != fortls_result.get("reference_probes"):
        diffs.append("reference probes differ:")
        diffs.append(
            diff_json(
                freight_result.get("reference_probes") or {},
                fortls_result.get("reference_probes") or {},
            )
        )
    if freight_result.get("implementation_probes") != fortls_result.get("implementation_probes"):
        diffs.append("implementation probes differ:")
        diffs.append(
            diff_json(
                freight_result.get("implementation_probes") or {},
                fortls_result.get("implementation_probes") or {},
            )
        )
    if freight_result.get("signature_probes") != fortls_result.get("signature_probes"):
        diffs.append("signature probes differ:")
        diffs.append(
            diff_json(
                freight_result.get("signature_probes") or {},
                fortls_result.get("signature_probes") or {},
            )
        )
    missing_completion_probes = {
        key: {"freight": (freight_result.get("completion_probes") or {}).get(key), "fortls": True}
        for key, value in (fortls_result.get("completion_probes") or {}).items()
        if value is True and (freight_result.get("completion_probes") or {}).get(key) is not True
    }
    if missing_completion_probes:
        diffs.append("completion probes missing from Freight:")
        diffs.append(json.dumps(missing_completion_probes, indent=2, sort_keys=True))
    if freight_result.get("rename_probes") != fortls_result.get("rename_probes"):
        diffs.append("rename probes differ:")
        diffs.append(
            diff_json(
                freight_result.get("rename_probes") or {},
                fortls_result.get("rename_probes") or {},
            )
        )
    missing_folding_probes: dict[str, list[dict[str, int]]] = {}
    freight_folds = freight_result.get("folding_probes") or {}
    for file_name, fortls_spans in (fortls_result.get("folding_probes") or {}).items():
        if method_not_found(fortls_spans):
            freight_spans = freight_folds.get(file_name)
            if not isinstance(freight_spans, list) or not freight_spans:
                missing_folding_probes[file_name] = [{"startLine": -1, "endLine": -1}]
            continue
        if not isinstance(fortls_spans, list):
            if freight_folds.get(file_name) != fortls_spans:
                missing_folding_probes[file_name] = fortls_spans
            continue
        freight_spans = {
            (span.get("startLine"), span.get("endLine"))
            for span in freight_folds.get(file_name, [])
            if isinstance(span, dict)
        }
        missing = [
            span
            for span in fortls_spans
            if isinstance(span, dict)
            and (span.get("startLine"), span.get("endLine")) not in freight_spans
        ]
        if missing:
            missing_folding_probes[file_name] = missing
    if missing_folding_probes:
        diffs.append("folding probes missing from Freight:")
        diffs.append(json.dumps(missing_folding_probes, indent=2, sort_keys=True))
    missing_semantic_probes: dict[str, Any] = {}
    freight_semantic = freight_result.get("semantic_probes") or {}
    for file_name, fortls_summary in (fortls_result.get("semantic_probes") or {}).items():
        freight_summary = freight_semantic.get(file_name)
        if method_not_found(fortls_summary):
            if not (
                isinstance(freight_summary, dict)
                and freight_summary.get("valid_token_count", 0) > 0
                and freight_summary.get("lines")
            ):
                missing_semantic_probes[file_name] = {
                    "freight": freight_summary,
                    "fortls": fortls_summary,
                }
            continue
        if not isinstance(fortls_summary, dict):
            if freight_summary != fortls_summary:
                missing_semantic_probes[file_name] = {
                    "freight": freight_summary,
                    "fortls": fortls_summary,
                }
            continue
        if not (
            isinstance(freight_summary, dict)
            and freight_summary.get("valid_token_count", 0) > 0
            and freight_summary.get("lines")
        ):
            missing_semantic_probes[file_name] = {
                "freight": freight_summary,
                "fortls": fortls_summary,
            }
    if missing_semantic_probes:
        diffs.append("semantic-token probes missing from Freight:")
        diffs.append(json.dumps(missing_semantic_probes, indent=2, sort_keys=True))

    return "\n".join(diffs)


def main() -> int:
    args = parse_args()
    freight = Path(args.freight).resolve()
    if not freight.is_file():
        print(f"ERROR: freight binary not found: {freight}", file=sys.stderr)
        print("Build it first with `cargo build -p freight`.", file=sys.stderr)
        return 2

    tmp_ctx = None
    if args.keep_fixture:
        root = Path(tempfile.mkdtemp(prefix="freight-fortran-lsp-"))
    else:
        tmp_ctx = tempfile.TemporaryDirectory(prefix="freight-fortran-lsp-")
        root = Path(tmp_ctx.name)
    try:
        project_mode = args.project is not None
        if project_mode:
            files = copy_project_fixture(args.project, root, args.max_files)
            if args.open_only:
                files = {k: v for k, v in files.items() if args.open_only in k}
                if not files:
                    print(f"ERROR: --open-only {args.open_only!r} matches no files", file=sys.stderr)
                    return 2
        else:
            files = make_fixture(root)
        if args.verbose and project_mode:
            print(f"Project fixture files ({len(files)}):")
            for name in files:
                print(f"  {name}")
        shim_dir = write_python_shims(root)
        env = os.environ.copy()
        python_path = f"{shim_dir}"
        if FORTLS_REFERENCE.is_dir():
            python_path = f"{python_path}{os.pathsep}{FORTLS_REFERENCE}"
        env["PYTHONPATH"] = f"{python_path}{os.pathsep}{env.get('PYTHONPATH', '')}"

        freight_proc = start_server([str(freight), "lsp", "--no-clangd", "--no-asm-lsp"], root)
        fortls_proc = start_server(
            args.fortls + ["--disable_autoupdate", "--incremental_sync", "--source_dirs", str(root)],
            root,
            env,
        )
        try:
            try:
                if project_mode:
                    freight_result = run_project_suite(
                        freight_proc,
                        "freight",
                        root,
                        files,
                        args.request_timeout,
                        args.diagnostic_timeout,
                        args.diagnostic_quiet,
                        args.settle_delay,
                        args.verbose,
                    )
                    fortls_result = run_project_suite(
                        fortls_proc,
                        "fortls",
                        root,
                        files,
                        args.request_timeout,
                        args.diagnostic_timeout,
                        args.diagnostic_quiet,
                        args.settle_delay,
                        args.verbose,
                    )
                else:
                    freight_result = run_suite(
                        freight_proc,
                        root,
                        files,
                        args.request_timeout,
                        args.diagnostic_timeout,
                        args.diagnostic_quiet,
                        args.settle_delay,
                        freight_native_extras=True,
                    )
                    fortls_result = run_suite(
                        fortls_proc,
                        root,
                        files,
                        args.request_timeout,
                        args.diagnostic_timeout,
                        args.diagnostic_quiet,
                        args.settle_delay,
                    )
            except RuntimeError as exc:
                print(f"ERROR: {exc}", file=sys.stderr)
                return 2
        finally:
            freight_proc.kill()
            fortls_proc.kill()

        if args.verbose:
            print("Freight:")
            print(json.dumps(freight_result, indent=2, sort_keys=True))
            print("fortls:")
            print(json.dumps(fortls_result, indent=2, sort_keys=True))

        mismatch = (
            project_diff(freight_result, fortls_result)
            if project_mode
            else (
                diff_json(freight_result["comparable"], fortls_result["comparable"])
                if freight_result["comparable"] != fortls_result["comparable"]
                else ""
            )
        )
        if mismatch:
            print("Fortran LSP differential mismatch:")
            print(mismatch)
            if args.keep_fixture:
                print(f"Fixture kept at {root}")
            return 1

        print("Fortran LSP differential check passed")
        if args.keep_fixture:
            print(f"Fixture kept at {root}")
        return 0
    finally:
        if tmp_ctx is not None:
            tmp_ctx.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
