# Production deployment

Production is noremac-prod, Tailscale 100.119.114.99. The old Pi
100.109.28.107 builds and tests; it must not serve the public production route.

The existing bare Git receiver remains on the build Pi. Its main push hook runs
scripts/update-pi-game.sh, which refuses dirty/diverged source, builds native and
WASM outputs, runs offline/browser checks, and invokes scripts/deploy-production.sh.
This stages a checksum-verified release on production and calls the fixed
root-owned activator. The activator switches /opt/starcoaster/current, updates the
service bind mount and library paths, tests an Electric Fields native session,
returns to the title screen, and restores the prior release on activation failure.
Browser input/render validation is an additional release check, not established
by the activator's native smoke test.

One-time installation on production:
sudo bash /home/cameron/starcoaster-deploy-setup/install-production-activator.sh

The dedicated builder key is allowed only from the build Pi's Tailscale address.
Only /usr/local/sbin/starcoaster-activate is passwordless; it accepts a full Git
revision or --check and only reads the fixed incoming directory. It extracts only
regular files/directories into a root-owned release. No licensed assets enter Git. Licensed game source files stay under
/var/lib/starcoaster/licensed. Private WASM outputs (including staged game graphics)
and compatibility libraries are transferred only over SSH.

The authenticated public Caddy site uses a reverse SSH tunnel:
old production 127.0.0.1:18091; new production 127.0.0.1:28091.
The new tunnel is cameron's starcoaster-production-tunnel user service with linger.
Keep the previous release and the old server's files for rollback. Stop and disable
the old public tunnel after validation and cutover. Mask the old production game
unit so outdated local deployment scripts cannot restart it.

Current rollout status: native startup, normal browser scenario selection,
Barracks construction, native Marine training, and browser movement passed on
production. Eight archive/activation tests passed, including simulated rollback.
The Caddy switch was attempted through the laptop, but the remote connection
timed out; verify the live upstream before stopping old services. The old game
and tunnel are still running. Privileged activator installation and a real
end-to-end automatic build/deploy remain gates. The activator installer is staged
on production at /home/cameron/starcoaster-deploy-setup/.

The build checkout is /media/pi/media1/starcoaster-production-build, with its
own clean main branch and build directories. The receive hook uses this checkout,
not the active phase1-map-loading-timings development branch. It fetches pinned
upstreams and bootstraps the ARM64 WASM toolchain on first use. First builds are
therefore substantially slower than incremental builds. The updater refuses a
pushed revision behind its checkout; merge the production-target changes before
the first production push. A successful push must match the revision deployed.
