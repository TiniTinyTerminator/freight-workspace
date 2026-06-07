#!/usr/bin/env python3
"""
Compare freight LSP inlay hints against clangd on examples/cpp/hello/src/main.cpp.

Usage:
    python3 scripts/lsp_hints_compare.py [--freight BIN] [--hello DIR]

Exits 0 if all non-IH-14 hints match, 1 otherwise.
"""

import subprocess, json, time, sys, argparse
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent.parent

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--freight", default=str(WORKSPACE / "target/debug/freight"))
    p.add_argument("--hello",   default=str(WORKSPACE / "crates/freight/examples/cpp/hello"))
    p.add_argument("--verbose", "-v", action="store_true")
    return p.parse_args()

# ── LSP wire helpers ──────────────────────────────────────────────────────────

def encode(msg: dict) -> bytes:
    body = json.dumps(msg).encode()
    return f"Content-Length: {len(body)}\r\n\r\n".encode() + body

def read_message(proc):
    headers = b""
    while True:
        ch = proc.stdout.read(1)
        if not ch: return None
        headers += ch
        if headers.endswith(b"\r\n\r\n"): break
    length = 0
    for line in headers.split(b"\r\n"):
        if line.lower().startswith(b"content-length:"):
            length = int(line.split(b":")[1].strip())
    return json.loads(proc.stdout.read(length))

def drain(proc, req_id, timeout=20.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        msg = read_message(proc)
        if msg is None: break
        if msg.get("id") == req_id: return msg
    return None

def start_server(cmd, cwd):
    return subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, cwd=cwd)

def do_initialize(proc, root_uri, rid=1):
    proc.stdin.write(encode({
        "jsonrpc": "2.0", "id": rid, "method": "initialize",
        "params": {
            "rootUri": root_uri,
            "capabilities": {"textDocument": {"inlayHint": {"dynamicRegistration": True}}},
            "initializationOptions": {},
        },
    }))
    proc.stdin.flush()
    drain(proc, rid)
    proc.stdin.write(encode({"jsonrpc": "2.0", "method": "initialized", "params": {}}))
    proc.stdin.flush()

def do_did_open(proc, uri, source):
    proc.stdin.write(encode({
        "jsonrpc": "2.0", "method": "textDocument/didOpen",
        "params": {"textDocument": {"uri": uri, "languageId": "cpp", "version": 1, "text": source}},
    }))
    proc.stdin.flush()
    time.sleep(1.5)

def do_hints(proc, uri, nlines, rid=10):
    proc.stdin.write(encode({
        "jsonrpc": "2.0", "id": rid, "method": "textDocument/inlayHint",
        "params": {
            "textDocument": {"uri": uri},
            "range": {"start": {"line": 0, "character": 0},
                      "end":   {"line": nlines - 1, "character": 0}},
        },
    }))
    proc.stdin.flush()
    return drain(proc, rid, timeout=25.0)

# ── Hint parsing ──────────────────────────────────────────────────────────────

def parse_hints(resp, skip_arrows=False):
    if not resp or resp.get("result") is None:
        return []
    out = []
    for h in (resp["result"] or []):
        pos  = h.get("position", {})
        line = pos.get("line", 0) + 1
        col  = pos.get("character", 0) + 1
        raw  = h.get("label", "")
        text = ("".join(p.get("value", "") if isinstance(p, dict) else str(p) for p in raw)
                if isinstance(raw, list) else str(raw))
        if skip_arrows and text.startswith("←"):
            continue
        out.append((line, col, h.get("kind", 0), text))
    return sorted(out)

KIND_NAME = {1: "type", 2: "param", 4: "blkend"}

def kind_str(k):
    return KIND_NAME.get(k, f"k{k}")

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    args = parse_args()
    hello = Path(args.hello)
    main_file = hello / "src/main.cpp"
    file_uri  = f"file://{main_file}"
    root_uri  = f"file://{hello}"
    cc_dir    = hello / ".freight/lsp/dev"

    if not main_file.is_file():
        print(f"ERROR: {main_file} not found — run `freight build` in {hello} first")
        sys.exit(1)
    if not cc_dir.is_dir():
        print(f"ERROR: {cc_dir} not found — run `freight lsp --no-clangd ...` once to generate compile_commands.json")
        sys.exit(1)

    source = main_file.read_text()
    nlines = source.count("\n") + 1

    print(f"Starting freight LSP ({args.freight}) …", end=" ", flush=True)
    freight = start_server([args.freight, "lsp", "--no-clangd", "--no-fortls", "--no-asm-lsp"], cwd=hello)
    do_initialize(freight, root_uri)
    do_did_open(freight, file_uri, source)
    print("ready")

    print("Starting clangd …", end=" ", flush=True)
    clangd = start_server(
        ["clangd", f"--compile-commands-dir={cc_dir}", "--background-index=false", "--header-insertion=never"],
        cwd=hello,
    )
    do_initialize(clangd, root_uri)
    do_did_open(clangd, file_uri, source)
    time.sleep(3.0)
    print("ready")

    fh_resp = do_hints(freight, file_uri, nlines)
    ch_resp = do_hints(clangd,  file_uri, nlines)

    freight.kill()
    clangd.kill()

    fh = parse_hints(fh_resp, skip_arrows=True)
    ch = parse_hints(ch_resp)
    src_lines = source.split("\n")

    # Collect all (line, col, kind) positions for comparison.
    # Excluded from matching (freight extensions / known gaps):
    #   kind 4 (blkend)  — freight-only; clangd disables these by default (IH-15)
    #   kind 0 with "[N]=" label — clangd designator hints (IH-14, not yet implemented)
    designator_cols = {c for _, c, k, t in ch if k == 0 and t.endswith("]=") }
    all_pos = sorted(set(
        (l, c, k) for l, c, k, _ in fh + ch
        if k != 4 and not (k == 0 and c in designator_cols)
    ))

    mismatches = []
    matches    = 0

    header = f"  {'L:C':7}  {'KIND':5}  {'FREIGHT':40}  {'CLANGD':40}  OK?"
    rows   = []
    for l, c, k in all_pos:
        fl = [t for ll, cc, kk, t in fh if ll == l and cc == c and kk == k]
        cl = [t for ll, cc, kk, t in ch if ll == l and cc == c and kk == k]
        ok = fl == cl
        if ok:
            matches += 1
        else:
            mismatches.append((l, c, k, fl, cl))
        src_snip = src_lines[l - 1].strip()[:38] if l <= len(src_lines) else ""
        sym = "✓" if ok else "✗"
        rows.append((ok, f"  L{l:2d}C{c:2d}  {kind_str(k):5}  {str(fl):40}  {str(cl):40}  {sym}  {src_snip}"))

    if args.verbose or mismatches:
        print(header)
        for _, row in rows:
            print(row)

    # Always print summary
    total = matches + len(mismatches)
    print(f"\n{matches}/{total} hints match clangd", end="")
    if mismatches:
        print(f"  ({len(mismatches)} mismatch{'es' if len(mismatches) != 1 else ''})")
        if not args.verbose:
            print("  (run with -v to see all hints)")
        for l, c, k, fl, cl in mismatches:
            src_snip = src_lines[l - 1].strip()[:50] if l <= len(src_lines) else ""
            print(f"  ✗ L{l}C{c} {kind_str(k)}: freight={fl!r}  clangd={cl!r}  |  {src_snip}")
        sys.exit(1)
    else:
        print()
        sys.exit(0)

if __name__ == "__main__":
    main()
