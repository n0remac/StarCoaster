#!/usr/bin/env bash
# Releases contain independent regular files, including aliased scenario inputs.
set -euo pipefail
[[ $# == 2 ]] || { echo 'Usage: package-production-archive.sh STAGE ARCHIVE' >&2; exit 2; }
tar --dereference --hard-dereference -cf "$2" -C "$1" .
