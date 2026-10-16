package main

import (
	"fmt"
	"regexp"
	"strconv"

	"starcoaster/internal/world"
)

var waveRequestID = regexp.MustCompile(`^([0-9a-f]{32}):wave:([0-9]+):([0-9]+)$`)

type scenarioWaveRequest struct {
	RequestID   string `json:"request_id"`
	PlayerID    int    `json:"player_id"`
	CommanderID int    `json:"commander_id"`
}

type scenarioWaveResponse struct {
	RequestID string `json:"request_id"`
	Accepted  bool   `json:"accepted"`
	WaveID    string `json:"wave_id"`
	State     string `json:"state"`
	Reason    string `json:"reason"`
}

func (s *service) respondWave(p *peer, m world.Envelope, requestID, waveID, state, reason string) {
	accepted := reason == ""
	// The envelope was delivered; application acceptance is reported separately.
	s.ack(p, m, true, "")
	_ = s.emit(p, "scenario.wave.status", s.registry.Session, s.registry.Revision,
		scenarioWaveResponse{RequestID: requestID, Accepted: accepted, WaveID: waveID, State: state, Reason: reason})
}

func (s *service) parkWaveRequest(p *peer, m world.Envelope) {
	var request scenarioWaveRequest
	if m.Decode(&request) != nil {
		s.respondWave(p, m, "", "", "rejected", "invalid_wave_request")
		return
	}
	parts := waveRequestID.FindStringSubmatch(request.RequestID)
	player, sequence := -1, -1
	if len(parts) == 4 {
		player, _ = strconv.Atoi(parts[2])
		sequence, _ = strconv.Atoi(parts[3])
	}
	if len(parts) != 4 || sequence < 1 || player != request.PlayerID ||
		request.PlayerID < 0 || request.PlayerID != request.CommanderID ||
		parts[1] != m.Session {
		s.respondWave(p, m, request.RequestID, "", "rejected", "invalid_or_unauthorized_wave_request")
		return
	}
	if m.Session != s.registry.Session || m.Revision != s.registry.Revision {
		s.respondWave(p, m, request.RequestID, "", "rejected", "stale_session_or_revision")
		return
	}
	if s.scenario == nil || s.scenario.Mode != "park_defense" || s.runtime == nil {
		s.respondWave(p, m, request.RequestID, "", "rejected", "park_defense_unavailable")
		return
	}
	if existing, ok := s.runtime.ManualRequests[request.RequestID]; ok {
		s.respondWave(p, m, request.RequestID, existing, "queued", "")
		return
	}
	if !s.ready || s.bw == nil || s.controller == nil || s.spawns == nil ||
		s.runtime.Error != "" || !s.runtime.Started {
		s.respondWave(p, m, request.RequestID, "", "rejected", "native_participants_unavailable")
		return
	}
	count := s.scenario.ParkDefense.UnitsPerWave
	if s.lastMarines+s.lastZerglings+s.spawns.PendingCount()+count > s.actorLimit() ||
		s.spawns.PendingCount()+count > 64 {
		s.respondWave(p, m, request.RequestID, "", "rejected", "spawn_capacity_unavailable")
		return
	}
	if s.parkPatch == nil && s.targetPatch == nil {
		zoneID := s.scenario.ParkDefense.SpawnZones[(s.runtime.NextWaveSequence-1)%len(s.scenario.ParkDefense.SpawnZones)]
		if _, ok := s.scenarioZoneCandidate(s.scenario.SpawnZones[zoneID], nil); !ok {
			s.respondWave(p, m, request.RequestID, "", "rejected", "no_eligible_spawn_zone_tile")
			return
		}
	}
	waveID, err := s.runtime.RequestManual(s.scenario, request.RequestID, request.PlayerID, sequence)
	if err != nil {
		s.respondWave(p, m, request.RequestID, "", "rejected", err.Error())
		return
	}
	if !s.saveScenarioRuntime() {
		s.scenarioRuntimeError(fmt.Errorf("scenario_journal_unavailable"))
		s.respondWave(p, m, request.RequestID, "", "rejected", "scenario_journal_unavailable")
		return
	}
	s.respondWave(p, m, request.RequestID, waveID, "queued", "")
	s.publishScenarioStatus(false)
}
