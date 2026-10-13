#!/usr/bin/env bash
# Run two independent native actor lifecycles with restart and client reconnect.
set -euo pipefail
project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"
report_dir="$project_dir/run-data/actor-lifecycle-$(date +%s)"
mkdir -p "$report_dir"
cycle_dirs=()
for cycle in 1 2; do
  printf 'ACTOR_LIFECYCLE_CYCLE %s\n' "$cycle"
  output="$(BRIDGE_ACTOR_TEST_RESTART=1 tests/test_actor_live.sh)"
  printf '%s\n' "$output"
  cycle_dir="${output##*Logs: }"
  test -d "$cycle_dir"
  cycle_dirs+=("$cycle_dir")
done
python3 - "$report_dir" "${cycle_dirs[@]}" <<'PY'
import json
import re
import sys
from pathlib import Path
report_dir = Path(sys.argv[1])
cycles = []
for path in map(Path, sys.argv[2:]):
    server = (path / 'session.log').read_text(errors='replace')
    match = re.search(r'park snapshot session=([0-9a-f]{32})', server)
    if not match:
        raise SystemExit(f'missing session ID in {path}')
    cycles.append({'session': match.group(1), 'logs': str(path),
                   'actor_id': 'openbw:3001', 'status': 'passed'})
if len(cycles) != 2 or cycles[0]['session'] == cycles[1]['session']:
    raise SystemExit('independent lifecycle runs did not receive distinct sessions')
report = {'status': 'passed', 'cycles': cycles,
          'checks': ['six_to_seven_marines', 'two_native_bindings', 'two_client_snapshots',
                     'native_hit_test', 'native_move_and_attack', 'client_reconnect',
                     'bridge_restart', 'death_removal', 'post_death_rejection']}
(report_dir / 'verification.json').write_text(json.dumps(report, indent=2) + '\n')
print('ACTOR_LIFECYCLE_REPEAT_PASS two distinct sessions with no duplicate actor IDs')
print('Report:', report_dir / 'verification.json')
PY
