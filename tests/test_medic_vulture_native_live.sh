#!/usr/bin/env bash
# Focused pinned OpenBW test; both participants report the same native state.
set -euo pipefail
project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"
: "${RCT2_DATA_DIR:?Set RCT2_DATA_DIR}"
: "${STARCRAFT_DATA_DIR:?Set STARCRAFT_DATA_DIR}"
run_dir="$project_dir/run-data/medic-vulture-native-$(date +%s)"
mkdir -p "$run_dir"
map_file="$run_dir/mt-zergling.scm"
python3 scripts/create-world-base-map.py --scenario scenarios/mt-zergling/scenario.json --output "$map_file" >/dev/null
park_file="$project_dir/run-data/mt-zergling/save/mt-zergling.park"
test -s "$park_file"
session_pid=""
cleanup() {
  if [[ -n "$session_pid" ]]; then
    kill "$session_pid" 2>/dev/null || true
    wait "$session_pid" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM
BRIDGE_TEST_MEDIC_VULTURE_NATIVE=1 BRIDGE_MAP_FILE="$map_file" \
  BRIDGE_SCENARIO_CONFIG="$project_dir/scenarios/mt-zergling/scenario.json" \
  BRIDGE_RULES_CONFIG="$project_dir/scenarios/mt-zergling/mapping.json" \
  BRIDGE_DISABLE_ASSAULT_AI=1 BRIDGE_LAUNCH_CLIENT=0 \
  BRIDGE_SERVER_DATA_DIR="$run_dir/server" \
  timeout 210s scripts/run-world-session.sh "$park_file" > "$run_dir/session.log" 2>&1 &
session_pid=$!
start=$SECONDS
until grep -q '\[next-tech\] role=controller stage=removed' "$run_dir/session.log" 2>/dev/null; do
  if (( SECONDS - start > 195 )); then
    echo "Timed out waiting for native Medic/Vulture probe: $run_dir" >&2
    exit 1
  fi
  sleep 1
done
python3 - "$run_dir" <<'PY'
import json
import re
import sys
from pathlib import Path

run = Path(sys.argv[1])
log = (run / "session.log").read_text(errors="replace")
checks = {}

def stage(role, name):
    matches = re.findall(r"^\[next-tech\] role=" + role + r" stage=" + name + r" .*$", log, re.M)
    return matches[-1] if matches else ""

for role in ("controller", "publisher"):
    before, after = stage(role, "before"), stage(role, "after")
    done, healed, removed = (stage(role, name) for name in ("completed", "healed", "removed"))
    supply_before = re.search(r"supply=(\d+)", before)
    supply_after = re.search(r"supply=(\d+)", after)
    supply_removed = re.search(r"supply=(\d+)", removed)
    checks[f"{role}_academy_gate"] = "medic=0" in before and "academy=1" in after and "medic=0" in removed
    if role == "controller":
        checks["controller_native_availability"] = "medic=1" in after and "vulture=1" in after
        checks["controller_supply_limit_after_depot_loss"] = "vulture=0" in removed
    else:
        checks["publisher_cannot_issue_enemy_training"] = "medic=0" in after and "vulture=0" in after
    checks[f"{role}_depot_supply"] = bool(supply_before and supply_after and supply_removed
        and int(supply_after[1]) > int(supply_before[1])
        and supply_removed[1] == supply_before[1])
    checks[f"{role}_production_complete"] = bool(re.search(r"medic=\d+ vulture=\d+", done))
    checks[f"{role}_native_healing"] = "marine_hp=20" in stage(role, "damaged") and bool(
        re.search(r"marine_hp=([2-9]\d|\d{3,})", healed))
train = stage("controller", "train")
checks["native_training_charges"] = "medic=1 vulture=1" in train and "minerals=500->" in train
checks["native_heal_order"] = "accepted=1" in stage("controller", "heal_order")
(run / "verification.json").write_text(json.dumps({"checks": checks}, indent=2) + "\n")
print(json.dumps(checks, indent=2))
print(f"Native evidence: {run}")
if not all(checks.values()):
    raise SystemExit(1)
PY
