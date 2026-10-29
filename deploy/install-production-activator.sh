#!/usr/bin/env bash
set -Eeuo pipefail
[[ $EUID == 0 ]] || { echo 'Run with sudo.'; exit 1; }
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python3 -c 'import ast,sys; ast.parse(open(sys.argv[1]).read())' "$here/activate-production.py"
install -o root -g root -m 0755 "$here/activate-production.py" /usr/local/sbin/starcoaster-activate
rule="$(mktemp)"
trap 'rm -f "$rule"' EXIT
printf '%s\n' 'cameron ALL=(root) NOPASSWD: /usr/local/sbin/starcoaster-activate' > "$rule"
visudo -cf "$rule"
install -o root -g root -m 0440 "$rule" /etc/sudoers.d/starcoaster-deploy
/usr/local/sbin/starcoaster-activate --check
echo 'Production activation installed. Only the fixed StarCoaster activator is passwordless.'
