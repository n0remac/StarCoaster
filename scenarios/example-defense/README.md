# Example Defense

This package uses the playable terrain generator with one fewer shop. The
layout differs from Frontier while retaining its verified ridge and path ramps.
It exercises the same bridge with an eastern opening group and a later western
group. The authored objective description is player-facing text.

Run `scripts/project.sh start --scenario example-defense` for full bootstrap, or
`scripts/project.sh play example-defense` after building the engines.
Use `scripts/project.sh park example-defense` to regenerate the park and
`scripts/project.sh record --scenario example-defense --duration 85` to capture it.
The recorder uses generic scenario identity and client synchronization checks.
