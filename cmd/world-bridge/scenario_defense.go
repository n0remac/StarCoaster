package main

import (
	"errors"

	"starcoaster/internal/world"
)

// Requests arrive only on the park connection after the multiplayer plugin has
// checked event.player against the current commander. The bridge checks the
// forwarded identity, session, revision and native readiness again.
type defenseConfigRequest struct {
	PlayerID    int     `json:"player_id"`
	CommanderID int     `json:"commander_id"`
	Enabled     *bool   `json:"enabled,omitempty"`
	Anchor      *[2]int `json:"anchor,omitempty"`
}

type defenseConfigResponse struct {
	Accepted bool   `json:"accepted"`
	Reason   string `json:"reason"`
}

func (s *service) respondDefense(p *peer, m world.Envelope, err error) {
	reason := ""
	if err != nil {
		reason = err.Error()
	}
	s.ack(p, m, true, "")
	_ = s.emit(p, "scenario.defense.result", s.registry.Session, s.registry.Revision,
		defenseConfigResponse{Accepted: err == nil, Reason: reason})
}

func (s *service) parkDefenseConfig(p *peer, m world.Envelope) {
	var request defenseConfigRequest
	if m.Decode(&request) != nil || (request.Anchor == nil && request.Enabled == nil) ||
		request.PlayerID < 0 || request.PlayerID != request.CommanderID {
		s.respondDefense(p, m, errors.New("invalid_or_unauthorized_defense_request"))
		return
	}
	if m.Session != s.registry.Session || m.Revision != s.registry.Revision {
		s.respondDefense(p, m, errors.New("stale_session_or_revision"))
		return
	}
	if s.scenario == nil || s.scenario.Mode != "park_defense" ||
		!s.scenario.ParkDefense.ManualActivation || s.runtime == nil {
		s.respondDefense(p, m, errors.New("defense_configuration_unavailable"))
		return
	}
	if !s.ready || s.bw == nil || s.controller == nil || s.spawns == nil ||
		!s.runtime.Started || s.runtime.Error != "" || !s.nativeOccupancyComplete ||
		s.navigationMask.Width == 0 || s.parkPatch != nil || s.targetPatch != nil {
		s.respondDefense(p, m, errors.New("native_participants_unavailable"))
		return
	}
	prior := *s.runtime
	if request.Anchor != nil {
		if s.runtime.SpawnAnchor != nil && *request.Anchor == *s.runtime.SpawnAnchor {
			// Replaying an accepted selection leaves the zone and countdown intact.
		} else if s.runtime.DefenseEnabled {
			s.respondDefense(p, m, errors.New("disable_defense_before_changing_spawn"))
			return
		} else if s.runtime.TotalTriggered > 0 {
			s.respondDefense(p, m, errors.New("spawn_point_locked_after_first_wave"))
			return
		} else {
			zone, err := s.fixedDefenseZone(*request.Anchor)
			if err != nil {
				s.respondDefense(p, m, err)
				return
			}
			anchor := *request.Anchor
			s.runtime.SpawnAnchor = &anchor
			s.runtime.FixedSpawnZone = zone
		}
	}
	if request.Enabled != nil && *request.Enabled != s.runtime.DefenseEnabled {
		if *request.Enabled {
			if s.runtime.SpawnAnchor == nil || len(s.runtime.FixedSpawnZone.Tiles) == 0 {
				s.respondDefense(p, m, errors.New("select_spawn_point_first"))
				return
			}
			s.runtime.NextAutomaticFrame = s.runtime.LastFrame + s.scenario.ParkDefense.InitialDelayFrames
		} else {
			s.runtime.NextAutomaticFrame = 0
		}
		s.runtime.DefenseEnabled = *request.Enabled
	}
	if !s.saveScenarioRuntime() {
		*s.runtime = prior
		s.respondDefense(p, m, errors.New("scenario_journal_unavailable"))
		return
	}
	s.respondDefense(p, m, nil)
	s.publishScenarioStatus(false)
}

// The native navigation mask is the same mask sent to both OpenBW participants.
// Check nearby clear positions and a route toward the interior before accepting
// an anchor. Native placement still performs final unit-specific clearance.
func (s *service) fixedDefenseZone(anchor [2]int) (world.SpawnZone, error) {
	width, height := s.scenario.ParkSize[0], s.scenario.ParkSize[1]
	x, y := anchor[0], anchor[1]
	const edgeBand = 8
	if x < 2 || y < 2 || x >= width-2 || y >= height-2 ||
		(x >= edgeBand && y >= edgeBand && x < width-edgeBand && y < height-edgeBand) {
		return world.SpawnZone{}, errors.New("spawn_point_outside_park_edge_band")
	}
	zone := world.SpawnZone{}
	for radius := 0; radius <= 2; radius++ {
		for dy := -radius; dy <= radius; dy++ {
			for dx := -radius; dx <= radius; dx++ {
				if radius > 0 && max(defenseAbs(dx), defenseAbs(dy)) != radius {
					continue
				}
				tile := [2]int{x + dx, y + dy}
				if tile[0] < 2 || tile[1] < 2 || tile[0] >= width-2 || tile[1] >= height-2 {
					continue
				}
				one := world.SpawnZone{Tiles: [][2]int{tile}}
				if _, ok := s.scenarioZoneCandidate(one, nil); ok {
					zone.Tiles = append(zone.Tiles, tile)
				}
			}
		}
	}
	if len(zone.Tiles) < 4 {
		return world.SpawnZone{}, errors.New("spawn_point_has_insufficient_clear_tiles")
	}
	if !s.defenseRouteToInterior(zone.Tiles) {
		return world.SpawnZone{}, errors.New("spawn_point_has_no_interior_route")
	}
	return zone, nil
}

func defenseAbs(value int) int {
	if value < 0 {
		return -value
	}
	return value
}

func (s *service) defenseRouteToInterior(tiles [][2]int) bool {
	width, height := s.scenario.ParkSize[0], s.scenario.ParkSize[1]
	visited := make(map[[2]int]bool)
	queue := append([][2]int(nil), tiles...)
	for _, tile := range queue {
		visited[tile] = true
	}
	directions := [][2]int{{1, 0}, {-1, 0}, {0, 1}, {0, -1}}
	for head := 0; head < len(queue); head++ {
		tile := queue[head]
		interior := min(12, min(width, height)/3)
		if tile[0] >= interior && tile[1] >= interior && tile[0] < width-interior && tile[1] < height-interior {
			return true
		}
		for _, dir := range directions {
			next := [2]int{tile[0] + dir[0], tile[1] + dir[1]}
			if next[0] < 2 || next[1] < 2 || next[0] >= width-2 || next[1] >= height-2 || visited[next] {
				continue
			}
			nativeX := s.transform.X(next[0]*32 + 16)
			nativeY := s.transform.Y(next[1]*32 + 16)
			if s.navigationMask.BlockedPixel(nativeX, nativeY) {
				continue
			}
			visited[next] = true
			queue = append(queue, next)
		}
	}
	return false
}
