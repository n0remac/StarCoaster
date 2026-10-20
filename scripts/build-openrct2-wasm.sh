#!/usr/bin/env bash
# Build the same patched OpenRCT2 source as the native client with upstream's
# Emscripten configuration. Run on amd64 in the upstream image, or use a native
# ARM64 Emscripten toolchain with equivalent cross-compiled dependencies.
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"
export CCACHE_DIR="${CCACHE_DIR:-$project_dir/build/wasm-ccache}"
mkdir -p "$CCACHE_DIR"
if [[ "${OPENRCT2_WASM_LOCAL:-0}" == 1 && ! -x "$(command -v emcmake || true)" && -f "$project_dir/build/emsdk/emsdk_env.sh" ]]; then
    # shellcheck disable=SC1091
    source "$project_dir/build/emsdk/emsdk_env.sh"
fi
if [[ "${OPENRCT2_WASM_LOCAL:-0}" == 1 && -z "${OPENRCT2_WASM_DEPS:-}" ]]; then
    export OPENRCT2_WASM_DEPS="$project_dir/build/openrct2-wasm-deps"
fi
if [[ "${1:-}" == --help ]]; then
    cat <<'EOF'
Usage: scripts/project.sh build-wasm

On amd64, uses ghcr.io/openrct2/openrct2-build:26-emscripten by default.
Set OPENRCT2_WASM_IMAGE to select a different image. Set OPENRCT2_WASM_LOCAL=1
to use a native emcmake toolchain and OPENRCT2_WASM_DEPS for its prebuilt
Emscripten ICU, libzip, and zstd dependency tree (same layout as /ext in the
upstream image). Multiplayer uses pinned WASM OpenSSL by default. Set
OPENRCT2_WASM_NETWORK=0 for an offline build. Set BRIDGE_BUILD_JOBS to limit memory use.
EOF
    exit 0
fi
if [[ "${1:-}" == --inside ]]; then
    deps="${OPENRCT2_WASM_DEPS:-/ext}"
    network="${OPENRCT2_WASM_NETWORK:-1}"
    for path in "$deps/icu/icu4c/source/common" "$deps/libzip/build/lib/libzip.a" \
        "$deps/zstd/build/build/lib/libzstd.a"; do
        test -e "$path" || { printf 'Missing Emscripten dependency: %s\n' "$path" >&2; exit 1; }
    done
    command -v emcmake >/dev/null || { printf 'Missing emcmake in WASM toolchain.\n' >&2; exit 1; }
    network_flags=()
    if [[ "$network" == 1 ]]; then
        scripts/prepare-openrct2-wasm-openssl.sh
        openssl="$project_dir/build/openrct2-wasm-deps/openssl"
        network_flags=(-DDISABLE_NETWORK=OFF
            -DOPENSSL_INCLUDE_DIR="$openssl/include"
            -DOPENSSL_CRYPTO_LIBRARY="$openssl/libcrypto.a"
            -DOPENSSL_SSL_LIBRARY="$openssl/libssl.a"
            -DOPENSSL_USE_STATIC_LIBS=TRUE)
    else
        network_flags=(-DDISABLE_NETWORK=ON)
    fi
    cmake_flags='-s USE_SDL=2 -s USE_ZLIB=1 -s USE_BZIP2=1 -s USE_LIBPNG=1 -pthread -O3'
    link_flags="-Wno-pthreads-mem-growth -s SAFE_HEAP=0 -s ALLOW_MEMORY_GROWTH=1 -s MAXIMUM_MEMORY=4GB -s INITIAL_MEMORY=2GB -s STACK_SIZE=8388608 -s MIN_WEBGL_VERSION=2 -s MAX_WEBGL_VERSION=2 -s PTHREAD_POOL_SIZE=120 -pthread -s EXPORTED_RUNTIME_METHODS=ccall,FS,callMain,UTF8ToString,stringToNewUTF8 -lidbfs.js --use-preload-plugins -s MODULARIZE=1 -s EXPORT_NAME=OPENRCT2_WEB -Wl,--export-if-defined=LoadGameCallback -Wl,--export-if-defined=StarCoasterJoin"
    emcmake cmake -S "$project_dir/upstream/openrct2" -B "$project_dir/build/openrct2-wasm" -G Ninja \
        -DCMAKE_BUILD_TYPE=Release \
        -DENABLE_SCRIPTING=ON -DDISABLE_GUI=OFF -DDISABLE_OPENGL=ON \
        "${network_flags[@]}" -DDISABLE_HTTP=ON -DDISABLE_TTF=ON \
        -DDISABLE_FLAC=ON -DDISABLE_DISCORD_RPC=ON \
        -DICU_INCLUDE_DIR="$deps/icu/icu4c/source/common" \
        -DICU_DATA_LIBRARIES="$deps/icu/icu4c/source/lib/libicuuc.so" \
        -DICU_DT_LIBRARY_RELEASE="$deps/icu/icu4c/source/stubdata/libicudata.so" \
        -DLIBZIP_LIBRARIES="$deps/libzip/build/lib/libzip.a" \
        -DLIBZIP_INCLUDE_DIRS="$deps/libzip/lib;$deps/libzip/build" \
        -DZLIB_INCLUDE_DIRS="$deps/zlib/build" \
        -DZSTD_LIBRARIES="$deps/zstd/build/build/lib/libzstd.a" \
        -DZSTD_INCLUDE_DIRS="$deps/zstd/lib" \
        -DEMSCRIPTEN_FLAGS="$cmake_flags" \
        -DEMSCRIPTEN_EXPORTED_FUNCTIONS=_GetVersion,_main \
        -DEMSCRIPTEN_LDFLAGS="$link_flags"
    cmake --build "$project_dir/build/openrct2-wasm" --target openrct2 --parallel "${BRIDGE_BUILD_JOBS:-2}"
    exit 0
fi
if (( $# )); then printf 'Unknown build-wasm option: %s\n' "$1" >&2; exit 2; fi
if [[ "${OPENRCT2_WASM_LOCAL:-0}" != 1 ]]; then
    command -v docker >/dev/null || { printf 'Docker is required for the upstream WASM image.\n' >&2; exit 1; }
    if [[ "$(uname -m)" != x86_64 && "${OPENRCT2_WASM_ALLOW_EMULATION:-0}" != 1 ]]; then
        printf 'The upstream Emscripten image is amd64 only. On ARM64, install a native emcmake toolchain and cross-compiled /ext dependencies, then set OPENRCT2_WASM_LOCAL=1, or build on an amd64 Linux workstation and deploy the bundle to this Pi. Set OPENRCT2_WASM_ALLOW_EMULATION=1 to explicitly try the amd64 image under emulation.\n' >&2
        exit 1
    fi
else
    command -v emcmake >/dev/null || { printf 'Missing emcmake for native WASM build.\n' >&2; exit 1; }
fi
export BRIDGE_SPRITE_SOURCE="${BRIDGE_SPRITE_SOURCE:-starcraft-local}"
python3 scripts/check-dependencies.py
python3 scripts/generate-starcraft-types.py --check
scripts/apply-openrct2-patches.sh

build_dir="$project_dir/build/openrct2-wasm"
bundle_dir="$project_dir/build/wasm-client"
jobs="${BRIDGE_BUILD_JOBS:-2}"
deps="${OPENRCT2_WASM_DEPS:-/ext}"
image="${OPENRCT2_WASM_IMAGE:-ghcr.io/openrct2/openrct2-build:26-emscripten}"
build_command=(bash scripts/build-openrct2-wasm.sh --inside)
if [[ "${OPENRCT2_WASM_LOCAL:-0}" != 1 ]]; then
    docker run --rm --platform linux/amd64 \
        --user "$(id -u):$(id -g)" \
        -v "$project_dir:$project_dir" -w "$project_dir" \
        -e BRIDGE_BUILD_JOBS="$jobs" -e OPENRCT2_WASM_DEPS=/ext \
        -e OPENRCT2_WASM_NETWORK="${OPENRCT2_WASM_NETWORK:-1}" \
        "$image" "${build_command[@]}"
else
    "${build_command[@]}"
fi

test -s "$build_dir/openrct2.js"
test -s "$build_dir/openrct2.wasm"
python3 scripts/package-openrct2-wasm.py "$build_dir" "$bundle_dir"
printf 'WASM bundle: %s\n' "$bundle_dir"

exit 0
