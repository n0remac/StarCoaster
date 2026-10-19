#!/usr/bin/env bash
# Build the network crypto dependency for the Emscripten OpenRCT2 client.
set -euo pipefail
project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if ! command -v emcc >/dev/null && [[ -f "$project_dir/build/emsdk/emsdk_env.sh" ]]; then
    # shellcheck disable=SC1091
    source "$project_dir/build/emsdk/emsdk_env.sh" >/dev/null
fi
command -v emcc >/dev/null || { printf 'Missing emcc for WASM OpenSSL build\n' >&2; exit 1; }
source_dir="$project_dir/build/openrct2-wasm-deps/openssl"
commit=a279090b9cd6b682a5a178410765a63e619fa2d9
if [[ ! -d "$source_dir/.git" ]]; then
    git clone --depth 1 --branch openssl-3.0.22 https://github.com/openssl/openssl.git "$source_dir"
fi
actual="$(git -C "$source_dir" rev-parse HEAD)"
[[ "$actual" == "$commit" ]] || { printf 'OpenSSL checkout mismatch: %s != %s\n' "$actual" "$commit" >&2; exit 1; }
if [[ -s "$source_dir/libcrypto.a" && -s "$source_dir/libssl.a" ]]; then
    printf 'WASM OpenSSL libraries already built: %s\n' "$source_dir"
    exit 0
fi
(
    cd "$source_dir"
    CC=emcc AR=emar RANLIB=emranlib ./Configure linux-generic32 \
        no-asm no-shared no-module no-tests no-afalgeng \
        --prefix="$project_dir/build/openrct2-wasm-deps/openssl-install"
    make -j "${BRIDGE_BUILD_JOBS:-2}" build_libs
)
test -s "$source_dir/libcrypto.a"
test -s "$source_dir/libssl.a"
printf 'WASM OpenSSL libraries built: %s\n' "$source_dir"
