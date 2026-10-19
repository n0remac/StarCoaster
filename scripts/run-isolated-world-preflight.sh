#!/usr/bin/env bash
# Called inside an unshared user/network namespace by the park supervisor.
set -euo pipefail
project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ip link set lo up
exec "$project_dir/scripts/run-world-session.sh" "${1:?Pass the prepared working park}"
