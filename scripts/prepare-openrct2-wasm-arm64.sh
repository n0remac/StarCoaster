#!/usr/bin/env bash
# Reproduce OpenRCT2's 26-emscripten toolchain on ARM64 using the attached
# build drive. Versions and dependency commands follow the upstream image.
set -euo pipefail
project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
emsdk="$project_dir/build/emsdk"
deps="$project_dir/build/openrct2-wasm-deps"
jobs="${BRIDGE_BUILD_JOBS:-2}"
mkdir -p "$project_dir/build"
if [[ ! -d "$emsdk/.git" ]]; then
    git clone --depth 1 https://github.com/emscripten-core/emsdk.git "$emsdk"
fi
"$emsdk/emsdk" install 5.0.0
"$emsdk/emsdk" activate 5.0.0
# shellcheck disable=SC1091
source "$emsdk/emsdk_env.sh"
if [[ "$(emcc -dumpmachine)" != wasm32-unknown-emscripten ]]; then
    printf 'Emscripten target is not wasm32\n' >&2; exit 1
fi
mkdir -p "$emsdk/upstream/emscripten/cache/sysroot/include" "$deps"
cp -a /usr/include/nlohmann "$emsdk/upstream/emscripten/cache/sysroot/include/"
clone_tag() {
    local dir="$1" repo="$2" tag="$3"
    if [[ ! -d "$deps/$dir/.git" ]]; then
        git clone --depth 1 --branch "$tag" "$repo" "$deps/$dir"
    fi
    test "$(git -C "$deps/$dir" describe --tags --exact-match)" == "$tag" || {
        printf 'Dependency %s is not at %s\n' "$dir" "$tag" >&2; exit 1;
    }
}
clone_tag icu https://github.com/unicode-org/icu.git release-77-1
clone_tag libzip https://github.com/nih-at/libzip.git v1.11.4
clone_tag zlib https://github.com/madler/zlib.git v1.3.1
clone_tag zstd https://github.com/facebook/zstd.git v1.5.7

icu_source="$deps/icu/icu4c/source"
if [[ ! -f "$deps/.icu-ready" ]]; then
    (
        cd "$icu_source"
        ac_cv_namespace_ok=yes icu_cv_host_frag=mh-linux emmake ./configure \
            --enable-release --enable-shared --disable-icu-config \
            --disable-extras --disable-icuio --disable-layoutex \
            --disable-tools --disable-tests --disable-samples
        # OpenRCT2 links ICU uc and stubdata only. The upstream image builds
        # ICU's default all target; on the Pi, avoid its unrelated i18n library.
        emmake make -C stubdata -j"$jobs"
        emmake make -C common -j"$jobs"
    )
    test -s "$icu_source/lib/libicuuc.so"
    test -s "$icu_source/stubdata/libicudata.so"
    touch "$deps/.icu-ready"
fi

if [[ ! -f "$deps/zlib/build/libz.a" ]]; then
    emcmake cmake -S "$deps/zlib" -B "$deps/zlib/build" -G "Unix Makefiles"
    emmake make -C "$deps/zlib/build" zlib -j"$jobs"
fi
# Upstream installs zlib into its container sysroot before building libzip.
# Keep the public header beside CMake's generated zconf.h in this local tree.
cp "$deps/zlib/zlib.h" "$deps/zlib/build/zlib.h"
if [[ ! -f "$deps/libzip/build/lib/libzip.a" ]]; then
    emcmake cmake -S "$deps/libzip" -B "$deps/libzip/build" -G "Unix Makefiles" \
        -DZLIB_INCLUDE_DIR="$deps/zlib/build" \
        -DZLIB_LIBRARY="$deps/zlib/build/libz.a"
    emmake make -C "$deps/libzip/build" zip -j"$jobs"
fi
if [[ ! -f "$deps/zstd/build/build/lib/libzstd.a" ]]; then
    emcmake cmake -S "$deps/zstd/build/cmake" -B "$deps/zstd/build/build" -G "Unix Makefiles" \
        -DZSTD_BUILD_STATIC=ON -DZSTD_BUILD_SHARED=OFF -DZSTD_BUILD_PROGRAMS=OFF
    emmake make -C "$deps/zstd/build/build" -j"$jobs"
fi
printf 'ARM64 WASM toolchain ready: %s\n' "$deps"
