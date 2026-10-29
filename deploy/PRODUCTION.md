# StarCoaster production delivery

Development happens in /media/pi/media1/rts-bridge on the 8 GB dev Pi.
GitHub (n0remac/StarCoaster) main is the only release source. Feature branches
do not deploy. Push a feature branch, merge reviewed/tested work into main, and
the dev Pi checks GitHub within two minutes. Direct pushes to main also trigger
the same path. A local Git receive hook can wake the worker early, but cannot
substitute a local-only revision for GitHub main.

## Build and release

The user timer starcoaster-deploy.timer starts starcoaster-deploy.service.
It survives logout/reboot through user lingering. Builds use their own clean
main checkout at /media/pi/media1/starcoaster-production-build, separate from
active development. A lock prevents overlapping releases. Failed checks leave
the existing production release running.

1. Fetch GitHub main, require a clean fast-forward, and compare its SHA to
   /opt/starcoaster/current/REVISION on the new Pi.
2. Verify deployment access; fetch pinned engine sources and prepare the ARM64
   Emscripten toolchain; build native engines, bridge and browser bundle.
3. Run Go, C++, Python, JavaScript, bundle and browser checks. Launch an isolated
   candidate on loopback port 18095 (native ports 11853/41110–41112).
   The browser selects Bumbly Bazaar, builds a Barracks, trains a Marine, issues
   movement and verifies native multiplayer traffic and actor movement.
4. Package a clean source/build snapshot with its full Git revision and checksums.
   Upload over SSH to 100.119.114.99, then rename the completed upload.
5. The root-owned starcoaster-activate helper extracts only relative regular
   files/directories, verifies checksums, switches the current release and matching
   browser bundle, and restarts starcoaster.service. An Electric Fields native
   startup and stability check must pass. Activation failure restores the old
   release, bundle and service configuration.

Deployment restarts game sessions. Saved parks and licensed data live separately
under /var/lib/starcoaster. Only the fixed activator is passwordless; its installer
is deploy/install-production-activator.sh. Engine binaries and licensed browser
graphics travel privately over SSH and must never be committed to Git.

The new Pi is noremac-prod (100.119.114.99). Its public tunnel now owns VPS loopback
port 18091, the existing authenticated Caddy upstream for starcoaster.noremac.dev.
A second production tunnel on port 28091 is also available. Both tunnels run on
the new Pi. The old Pi's game and public tunnel units are stopped and disabled;
it now serves as the development/build host.

## Operating the pipeline

On the dev Pi:

    systemctl --user status starcoaster-deploy.timer starcoaster-deploy.service
    journalctl _SYSTEMD_USER_UNIT=starcoaster-deploy.service -n 80 --no-pager
    cat /media/pi/media1/starcoaster-production-build/run-data/deployment-status.json

To check GitHub immediately:

    systemctl --user start --no-block starcoaster-deploy.service

The status file records the source revision, stage, timestamp and success/failure.
run-data/prod-deployed-revision is a convenience marker; production's actual
REVISION and active service are authoritative. Browser evidence is in
build/release-browser/runtime.json and screenshots. First builds can be slow;
later builds reuse isolated compiler/build caches.

The timer retries failed checks. An extracted release whose activation failed is
retained for investigation: publish a corrected commit instead of overwriting an
existing release directory. /opt/starcoaster/previous preserves the last good
release. Rollback tests exercise restoration of release, bundle and config.

The pipeline is local systemd CI/CD, not a GitHub Actions workflow. GitHub commit
status reporting/alerts, protected-main review requirements, and maintenance-aware
deployment scheduling are useful follow-up improvements.
