# v0.2 recording and performance

The Frontier recorder now uses the shared `VideoRecorder` for one client, a side-by-side two-client video, or separate client files. `--no-video` runs the same graphical capture without FFmpeg. FPS, per-client output width, display size, x264 preset and CRF, graphics mode, and frame pacing are command-line settings. Each artifact run keeps screenshots, filtered logs, video metadata, verification results, and validated MP4s in the viewer.

On this Raspberry Pi, `scripts/benchmark-video-capture.py --modes off 15 30 --seconds 20 --layout single --video-width 800` and the same command with `--layout combined` produced:

| Layout | FPS | Client A tick span | Client B tick span | Measured video FPS | FFmpeg CPU, one core |
| --- | ---: | ---: | ---: | ---: | ---: |
| Single | Off | 1,038 | — | — | 0% |
| Single | 15 | 1,053 | — | 15.0 | 22.9% |
| Single | 30 | 1,063 | — | 30.0 | 44.4% |
| Combined | Off | 1,499 | 1,193 | — | 0% |
| Combined | 15 | 1,539 | 1,234 | 15.0 | 49.4% |
| Combined | 30 | 1,523 | 1,234 | 30.0 | 97.7% |

Both clients continued advancing at comparable rates with and without capture. The combined 30 FPS encode used almost a full CPU core; 15 FPS at 800 pixels per client is the default Pi setting with more headroom. These are 20-second, sequential runs, so minor tick differences include startup and sampling variation. The summary JSON files are in `run-data/frontier-v02-benchmark-summary.json` and `run-data/frontier-v02-two-client-benchmark-summary.json`; each row points to its artifact viewer run.

The previous laggy recordings were consistent with capture cost rather than an observed simulation stall in this benchmark. The longer combat capture below exercises scene-dependent encoder load; thermal behavior beyond that session remains unmeasured.

An 85-second two-client combat recording used 15 FPS combined capture at 800 pixels per client. `VideoRecorder` validated 1,270 frames at 15.0 FPS over 84.667 seconds. The artifact at `run-data/artifacts/20261012T233122Z-01c58848c6db/` includes twelve screenshots, filtered logs, configuration, verification JSON, video metadata, and the combined MP4. All 459 shared snapshot sequences matched through combat and carousel demolition, with no mismatch recorded. This longer run did not exercise drag selection or wall demolition, so its gameplay verifier correctly reports `demonstration_complete: false` while the capture and synchronization checks pass.
