# Remote test artifact viewer

The read-only Go viewer indexes `run-data/artifacts/`. Each new graphical capture or battle replay creates a unique run directory and an atomic `run.json`. It does not need OpenRCT2 or OpenBW to be running. All completed runs are retained until removed manually. A failed capture retains its completed screenshots, validated video, verification result, and filtered diagnostic logs.

Live capture video comes from two graphical OpenRCT2 clients. Battle replay video is an OpenBW trace **composited over a static OpenRCT2 park screenshot**; it is not live synchronized OpenRCT2 combat.

## Build and run on the Pi

Go 1.25 or later is required. On this Pi, Go is installed at `/usr/local/go/bin/go`.

```sh
cd ~/Projects/rts-bridge
/usr/local/go/bin/go test ./...
python3 -m unittest discover -s tests -p 'test_*.py'
/usr/local/go/bin/go build -o build/test-viewer ./cmd/test-viewer
STARCOASTER_ARTIFACT_ROOT="$PWD/run-data/artifacts" build/test-viewer
```

The default listener is `127.0.0.1:8787`. `STARCOASTER_VIEWER_LISTEN` changes it. `STARCOASTER_ARTIFACT_ROOT` changes storage. `STARCOASTER_VIEWER_MAX_RUNS` optionally caps list page size; it never deletes artifacts. Test locally with `curl -f http://127.0.0.1:8787/healthz` and open `http://127.0.0.1:8787/` on the Pi.

## Capture runs

The current command lines continue to work. Without an output override, each invocation uses a new directory under `run-data/artifacts/`:

```sh
DEMO_PARK=run-data/park-generator/save/bridge-render-test.park \
  python3 scripts/capture-live-demo.py --seconds 8 --record-video
python3 scripts/render-battle-replay.py
python3 scripts/capture-live-demo.py --scenario ride-siege --verify-destruction \
  --record-video --video-layout combined
```

`DEMO_OUTPUT_DIR=run-data/my-demo` and battle replay `--output run-data/my-replay` still write there. A separate unique artifact directory receives copies of approved files when the command exits, including failures. The original output is left at the requested path. The viewer only advertises an MP4 after FFmpeg has exited and `ffprobe` has validated it. Other runtime files, extracted sprites, archives, and build assets are not published.

The ride siege capture is a live two-client interaction with a real OpenRCT2 ride. See the [ride siege guide](ride-siege.md). Its detail page shows the OpenBW target HP events, native demolition result, and each client's ride and track state, alongside the combined recording and screenshots.

## User service

The included unit uses `~/Projects/rts-bridge`; edit it first if your clone is elsewhere.

```sh
cd ~/Projects/rts-bridge
/usr/local/go/bin/go build -o build/test-viewer ./cmd/test-viewer
mkdir -p ~/.config/systemd/user
cp deploy/starcoaster-test-viewer.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now starcoaster-test-viewer.service
sudo loginctl enable-linger "$USER"
systemctl --user status starcoaster-test-viewer.service
journalctl --user -u starcoaster-test-viewer.service -f
```

`enable-linger` allows the user service to start at boot without a login. Rebuild the binary and use `systemctl --user restart starcoaster-test-viewer.service` after code changes. Application diagnostics go to journald.

## Private Tailscale HTTPS

Inspect the existing configuration first:

```sh
tailscale version
tailscale serve status --json
tailscale funnel status
```

On this Pi, Tailscale 1.102.2 already uses public Funnel port 443 for a Fabric endpoint at `http://127.0.0.1:8080`. Leave that route intact. The installed CLI accepts a separate HTTPS port:

```sh
sudo tailscale serve --bg --https=8443 http://127.0.0.1:8787
tailscale serve status --json
tailscale status --json | python3 -c 'import json,sys; print(json.load(sys.stdin)["Self"]["DNSName"])'
```

The private URL is `https://<DNSName>:8443/`. Confirm that `AllowFunnel` includes only the preexisting `:443` route and no `:8443` route. From a **second device joined to the same tailnet**, open that URL in a browser and check the latest run, MP4 playback and seeking, and full-size screenshots. Alternatively run `curl -f https://<DNSName>:8443/healthz` there. Do not use `tailscale funnel` or `tailscale serve reset` for this viewer. On this Pi, local DNS currently resolves the hostname to a public address; to test its private listener from the Pi itself, use `curl --resolve <DNSName>:8443:$(tailscale ip -4) https://<DNSName>:8443/healthz`.

## API and maintenance

`/api/runs` lists newest first. It accepts `status`, `type`, `limit`, and `offset`. `/api/runs/{id}` returns a run with parsed verification, video metadata, events, and bounded diagnostic previews. `/media/{id}/{filename}` serves only manifest-listed PNGs, validated MP4s, and filtered logs. The server has no write or execution endpoints.

Inspect storage with `du -sh run-data/artifacts/*`. To remove an old run, stop any capture that might be writing to its directory, then delete that specific run directory on the Pi. No automatic retention or HTTP deletion is implemented. A missing or malformed manifest is skipped. If a video is absent, inspect `video-metadata.json` in its run directory for `recording_errors`; the viewer intentionally hides unfinished recordings.
