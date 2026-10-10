#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
data_dir="${STARCRAFT_DATA_DIR:?Set STARCRAFT_DATA_DIR to your own StarCraft data directory}"
map_file="${BRIDGE_MAP_FILE:-$project_dir/upstream/bwapi/bwapi/TestAIModule/maps/TestModule/ZergTest.scm}"
launcher="$project_dir/build/bwapi/bin/BWAPILauncher"
module="$project_dir/build/bridge-module/BridgeAIModule.so"
runtime_dir="${BRIDGE_BWAPI_RUNTIME_DIR:-$project_dir/run-data/openbw}"

star_dat=""
broo_dat=""
for candidate in StarDat.mpq Stardat.mpq; do
  if test -f "$data_dir/$candidate"; then star_dat="$data_dir/$candidate"; break; fi
done
for candidate in BrooDat.mpq Broodat.mpq; do
  if test -f "$data_dir/$candidate"; then broo_dat="$data_dir/$candidate"; break; fi
done
test -n "$star_dat" || { printf 'Missing StarDat.mpq (or Stardat.mpq) in %s\n' "$data_dir" >&2; exit 1; }
test -n "$broo_dat" || { printf 'Missing BrooDat.mpq (or Broodat.mpq) in %s\n' "$data_dir" >&2; exit 1; }
test -f "$data_dir/Patch_rt.mpq" || { printf 'Missing Patch_rt.mpq in %s\n' "$data_dir" >&2; exit 1; }
test -f "$map_file" || { printf 'Missing map: %s\n' "$map_file" >&2; exit 1; }
case "${map_file##*.}" in
  scm|SCM|scx|SCX) ;;
  *) printf 'Map must have a .scm or .scx extension: %s\n' "$map_file" >&2; exit 1 ;;
esac
test -x "$launcher" || { printf 'Missing launcher; run scripts/build-bwapi.sh\n' >&2; exit 1; }
test -f "$module" || { printf 'Missing module; run scripts/build-bridge-module.sh\n' >&2; exit 1; }

mkdir -p "$runtime_dir/bwapi-data" "$runtime_dir/maps"
ln -sfn "$(realpath "$star_dat")" "$runtime_dir/StarDat.mpq"
ln -sfn "$(realpath "$broo_dat")" "$runtime_dir/BrooDat.mpq"
ln -sfn "$(realpath "$data_dir/Patch_rt.mpq")" "$runtime_dir/Patch_rt.mpq"
map_name="demo.${map_file##*.}"
ln -sfn "$(realpath "$map_file")" "$runtime_dir/maps/$map_name"

cat > "$runtime_dir/bwapi-data/bwapi.ini" <<EOF
[ai]
ai = $module

[auto_menu]
auto_menu = ${BRIDGE_BWAPI_MENU:-SINGLE_PLAYER}
map = maps/$map_name
race = ${BRIDGE_BWAPI_RACE:-Zerg}
enemy_count = 1
enemy_race = Terran
game_type = MELEE
auto_restart = OFF
EOF

export OPENBW_ENABLE_UI=0
export BRIDGE_MAP_ID="${BRIDGE_MAP_ID:-demo-flat}"
export LD_LIBRARY_PATH="$project_dir/build/bwapi/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
cd "$runtime_dir"
exec "$launcher"
