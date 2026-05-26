# Freight Registry — Setup & Usage Guide

Step-by-step instructions for running a freight registry server,
importing vcpkg packages, and connecting freight clients.

---

## 1. Start the registry server

```sh
# Build
cargo build -p freight-registry

# Run (development)
./target/debug/freight-registry \
    --data /var/lib/freight-registry \
    serve \
    --base-url http://my-server:7878 \
    --bind 0.0.0.0:7878

# For bulk import (raise rate limits)
./target/debug/freight-registry \
    --data /var/lib/freight-registry \
    serve \
    --base-url http://my-server:7878 \
    --rate-limit-write 10000
```

The `--data` directory is created automatically.  It contains:
- `freight.db` — SQLite database (WAL mode)
- `tarballs/` — stored source archives (empty for metadata-only packages)

---

## 2. Create a user and token

```sh
# Create an admin user
freight-registry --data /var/lib/freight-registry \
    user add admin --email admin@example.com --password <password>

# Create an API token
freight-registry --data /var/lib/freight-registry \
    token add publish --user admin
# Output: frt_<hex>   ← save this
```

---

## 3. Import vcpkg stubs

```sh
# Scrape the vcpkg port catalog
vcpkg-scraper scrape ~/vcpkg --out registry-out/

# Import into the running registry
vcpkg-scraper registry-import registry-out/ \
    --server http://my-server:7878 \
    --token frt_<your-token> \
    --continue   # skip already-imported packages on re-runs
```

The import prints one line per package:
```
[import] zlib@1.3.2
[import] abseil@20260107.1
...
Done. 2000 total  |  1850 imported  |  120 skipped (no url)  |  30 already existed  |  0 failed
```

Packages without a `url` field in their stub (e.g. header-only stubs
with no source archive) are skipped and counted as "no url".

---

## 4. Configure freight clients

### Option A: project-local config (`.freight/config.toml`)

Place this file in the project root (committed to VCS):

```toml
[[registries]]
name = ""           # "" = default registry (no "repo =" needed in freight.toml)
url  = "http://my-server:7878"
```

### Option B: user-global config (`~/.freight/config.toml`)

```toml
[[registries]]
name = ""
url  = "https://freight.mycompany.com"
token = "frt_<your-token>"   # optional; needed only for publishing
```

### Option C: environment variable

```sh
export FREIGHT_REGISTRY_URL=http://my-server:7878
```

---

## 5. Use registry packages in `freight.toml`

After import, packages can be referenced by name and version:

```toml
[dependencies]
zlib    = "1.3.2"
abseil  = "20260107.1"
openssl = "3.5.0"
```

`freight build` automatically:
1. Queries the registry for each version dep
2. Downloads the upstream source archive (via 302 redirect)
3. Detects the build system (`cmake`, `make`, etc.)
4. Builds and installs the dependency into `.deps/<name>/`
5. Links your project against the installed headers and libs

---

## 6. Verify a package

```sh
# Check what the registry knows about a package
curl http://my-server:7878/api/v1/packages/zlib | jq .

# Check the download redirect
curl -I http://my-server:7878/api/v1/packages/zlib/1.3.2/download
# HTTP/1.1 302 Found
# location: https://github.com/madler/zlib/archive/v1.3.2.tar.gz
```

---

## 7. Mirror mode (proxy upstream registry)

The server can proxy unknown packages from an upstream registry:

```sh
freight-registry serve \
    --mirror-upstream https://freight.dev
```

When a package is not found locally, the server transparently forwards
the request to the upstream and returns the result.

---

## File layout after `freight build`

```
myproject/
├── freight.toml
├── src/main.cpp
└── .deps/
    └── zlib/
        ├── .freight-fetched          ← sentinel (source was downloaded)
        ├── .freight-build-system     ← "cmake" (written by fetch_registry_deps)
        ├── CMakeLists.txt            ← upstream source
        ├── zlib.h, zconf.h, …
        └── .freight-build/
            └── install/
                ├── include/zlib.h    ← cmake-installed headers
                └── lib/libz.a        ← cmake-installed library
```
