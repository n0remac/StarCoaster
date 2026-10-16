package main

import (
	"encoding/json"
	"errors"
	"log"
	"os"
	"path/filepath"

	"starcoaster/internal/world"
)

type nativeSpawnStatus struct {
	RequestID string `json:"request_id"`
	Index     int    `json:"index"`
	State     string `json:"state"`
	ActorID   string `json:"actor_id,omitempty"`
	X         int    `json:"x,omitempty"`
	Y         int    `json:"y,omitempty"`
	Reason    string `json:"reason,omitempty"`
}

func (s *service) initSpawns(session string) {
	if s.spawns != nil && s.spawns.Session == session {
		return
	}
	limit := s.maxLiveActors
	if limit < 1 || limit > 256 {
		limit = 240
	}
	if s.spawnJournalPath != "" {
		data, err := os.ReadFile(s.spawnJournalPath)
		if err == nil {
			var saved world.SpawnQueue
			if json.Unmarshal(data, &saved) == nil && saved.Session == session &&
				saved.Recover(session, 64) == nil {
				s.spawns = &saved
				s.saveSpawns()
				return
			}
		}
	}
	s.spawns = world.NewSpawnQueue(session, 64)
	s.saveSpawns()
}

func (s *service) saveSpawns() bool {
	if s.spawnJournalPath == "" || s.spawns == nil {
		return true
	}
	data, err := json.Marshal(s.spawns)
	if err != nil {
		log.Printf("spawn journal encode: %v", err)
		return false
	}
	if err := os.MkdirAll(filepath.Dir(s.spawnJournalPath), 0700); err != nil {
		log.Printf("spawn journal directory: %v", err)
		return false
	}
	temporary := s.spawnJournalPath + ".tmp"
	if err := os.WriteFile(temporary, data, 0600); err != nil {
		log.Printf("spawn journal write: %v", err)
		return false
	}
	if err := os.Rename(temporary, s.spawnJournalPath); err != nil {
		log.Printf("spawn journal replace: %v", err)
		return false
	}
	return true
}

func (s *service) spawnStatus(status world.SpawnStatus) {
	if s.spawns != nil {
		if request, ok := s.spawns.Request(status.RequestID); ok && request.UnitType == "zerg_zergling" {
			wave := s.scenarioWaveForRequest(status.RequestID)
			if wave != "" {
				log.Printf("scenario spawn request=%s wave=%s state=%s", status.RequestID, wave, status.State)
			} else {
				log.Printf("scenario spawn request=%s state=%s", status.RequestID, status.State)
			}
			return
		}
	}
	_ = s.emit(s.park, "unit.spawn.status", s.registry.Session, s.registry.Revision, status)
}

func (s *service) scenarioWaveForRequest(requestID string) string {
	if s.runtime == nil {
		return ""
	}
	for _, wave := range s.runtime.Waves {
		for _, unit := range wave.Units {
			for _, attempt := range unit.Attempts {
				if attempt.RequestID == requestID {
					return wave.ID
				}
			}
		}
	}
	return ""
}

func (s *service) submitScenarioSpawns() {
	if s.scenario == nil || s.spawns == nil || s.outcome != "" || !s.ready {
		return
	}
	for _, wave := range s.scenario.SpawnWaves {
		request := world.SpawnRequest{RequestID: s.registry.Session + ":scenario:" + wave.ID,
			UnitType: wave.UnitType, Count: wave.Count, X: wave.X, Y: wave.Y,
			Formation: wave.Formation, PlayerID: 0}
		if _, exists := s.spawns.Request(request.RequestID); !exists {
			limit := s.maxLiveActors
			if limit < 1 || limit > 256 {
				limit = 240
			}
			living := s.lastMarines + s.lastZerglings
			starting := len(s.scenario.StartingUnits.Marines) + len(s.scenario.StartingUnits.Zerglings)
			if living < starting {
				living = starting
			}
			if living+s.spawns.PendingCount()+request.Count > limit {
				log.Printf("scenario spawn %s rejected: live_actor_limit", wave.ID)
				continue
			}
		}
		status, err := s.spawns.Submit(s.registry.Session, request)
		if err != nil {
			log.Printf("scenario spawn %s rejected: %v", wave.ID, err)
			continue
		}
		if !s.saveSpawns() {
			_, _ = s.spawns.Cancel(request.RequestID)
			continue
		}
		log.Printf("scenario spawn request=%s state=%s", request.RequestID, status.State)
	}
}

// scenarioZoneCandidate reads the latest complete native occupancy and the
// shared queue. It leaves the manual Marine request and placement flow alone.
func (s *service) scenarioZoneCandidate(zone world.SpawnZone, extra []world.Point) (world.Point, bool) {
	if !s.nativeOccupancyComplete || s.navigationMask.Width == 0 || s.spawns == nil {
		return world.Point{}, false
	}
	reserved := append([]world.Point(nil), extra...)
	offsets := [...]world.Point{{}, {X: 32}, {X: -32}, {Y: 32}, {Y: -32}}
	for _, id := range s.spawns.Order {
		request, ok := s.spawns.Request(id)
		if !ok {
			continue
		}
		status, ok := s.spawns.Lookup(id)
		if !ok {
			continue
		}
		for _, unit := range status.Units {
			// Ready actors are represented by the complete native occupancy.
			// Keeping their original queue tiles reserved after they move or die
			// can permanently exhaust a recurring perimeter zone.
			if unit.State != "ready" && unit.State != "failed" && unit.State != "rejected" {
				offset := offsets[unit.Index]
				reserved = append(reserved, world.Point{X: request.X + offset.X, Y: request.Y + offset.Y})
			}
		}
	}
	return world.SelectZonePosition(zone, s.navigationMask, s.transform, s.nativeOccupants, reserved)
}

func (s *service) rejectSpawn(p *peer, m world.Envelope, requestID, reason string) {
	s.ack(p, m, false, reason)
	if requestID != "" {
		s.spawnStatus(world.SpawnStatus{RequestID: requestID, State: "rejected", Reason: reason,
			Units: []world.SpawnUnitResult{}})
	}
}

func (s *service) parkSpawnMessage(p *peer, m world.Envelope) {
	if m.Kind == "unit.spawn.query" || m.Kind == "unit.spawn.cancel" {
		var query struct {
			RequestID string `json:"request_id"`
		}
		if m.Decode(&query) != nil || s.spawns == nil || m.Session != s.registry.Session {
			s.ack(p, m, false, "invalid_spawn_query")
			return
		}
		if m.Kind == "unit.spawn.cancel" {
			status, err := s.spawns.Cancel(query.RequestID)
			if err != nil {
				s.ack(p, m, false, err.Error())
				return
			}
			s.saveSpawns()
			s.ack(p, m, true, "")
			s.spawnStatus(status)
			return
		}
		status, ok := s.spawns.Lookup(query.RequestID)
		if !ok {
			s.ack(p, m, false, "unknown_spawn_request")
			return
		}
		s.ack(p, m, true, "")
		s.spawnStatus(status)
		return
	}
	var request world.SpawnRequest
	if m.Decode(&request) != nil {
		s.ack(p, m, false, "invalid_spawn_request")
		return
	}
	if s.spawns == nil || m.Session != s.registry.Session || m.Revision != s.registry.Revision {
		s.rejectSpawn(p, m, request.RequestID, "stale_session")
		return
	}
	if previous, ok := s.spawns.Request(request.RequestID); ok {
		if previous != request {
			s.rejectSpawn(p, m, request.RequestID, "conflicting_request_id")
			return
		}
		status, _ := s.spawns.Lookup(request.RequestID)
		s.ack(p, m, true, "")
		s.spawnStatus(status)
		return
	}
	if (!s.ready && s.parkPatch == nil) || s.outcome != "" || s.bw == nil || s.controller == nil {
		s.rejectSpawn(p, m, request.RequestID, "spawn_unavailable")
		return
	}
	if request.UnitType != "terran_marine" || request.PlayerID < 0 {
		s.rejectSpawn(p, m, request.RequestID, "unauthorized_spawn")
		return
	}
	if request.X < 0 || request.Y < 0 || request.X >= s.registry.Width*32 ||
		request.Y >= s.registry.Height*32 {
		s.rejectSpawn(p, m, request.RequestID, "invalid_spawn_position")
		return
	}
	limit := s.maxLiveActors
	if limit < 1 || limit > 256 {
		limit = 240
	}
	if s.lastMarines+s.lastZerglings+s.spawns.PendingCount()+request.Count > limit {
		s.rejectSpawn(p, m, request.RequestID, "live_actor_limit")
		return
	}
	status, err := s.spawns.Submit(m.Session, request)
	if err != nil {
		s.rejectSpawn(p, m, request.RequestID, err.Error())
		return
	}
	if !s.saveSpawns() {
		_, _ = s.spawns.Cancel(request.RequestID)
		s.rejectSpawn(p, m, request.RequestID, "spawn_journal_unavailable")
		return
	}
	s.ack(p, m, true, "")
	s.spawnStatus(status)
	s.pumpSpawns()
}

func (s *service) pumpSpawns() {
	if s.spawns == nil || !s.ready || s.parkPatch != nil || s.targetPatch != nil ||
		s.bw == nil || s.outcome != "" || (s.runtime != nil && s.runtime.Error != "") {
		return
	}
	execute, ok := s.spawns.Next()
	if !ok {
		return
	}
	if err := s.spawns.Issue(execute); err != nil {
		log.Printf("spawn issue: %v", err)
		return
	}
	if !s.saveSpawns() {
		_ = s.spawns.Fail(execute.RequestID, execute.Index, "spawn_journal_unavailable")
		if status, ok := s.spawns.Lookup(execute.RequestID); ok {
			s.spawnStatus(status)
		}
		return
	}
	execute.X = s.transform.X(execute.X)
	execute.Y = s.transform.Y(execute.Y)
	opID := "spawn:" + s.operation()
	if s.spawnOps == nil {
		s.spawnOps = map[string]world.SpawnExecute{}
	}
	s.spawnOps[opID] = execute
	message := world.Message("unit.spawn.execute", s.registry.Session, opID, "bridge", s.registry.Revision, execute)
	if err := s.bw.send(message); err != nil {
		delete(s.spawnOps, opID)
		if status, ok := s.spawns.Uncertain(); ok {
			s.saveSpawns()
			s.spawnStatus(status)
		}
		return
	}
	if status, ok := s.spawns.Lookup(execute.RequestID); ok {
		s.spawnStatus(status)
	}
}

func (s *service) reconcileUncertainSpawn() {
	if s.spawns == nil || s.bw == nil {
		return
	}
	execute, ok := s.spawns.Unresolved()
	if !ok {
		return
	}
	status, _ := s.spawns.Lookup(execute.RequestID)
	if status.Units[execute.Index].State != "uncertain" {
		return
	}
	_ = s.emit(s.bw, "unit.spawn.reconcile", s.registry.Session, s.registry.Revision,
		map[string]any{"pending": []map[string]any{{"request_id": execute.RequestID, "index": execute.Index}}})
}

func (s *service) bwSpawnMessage(p *peer, m world.Envelope) {
	var native nativeSpawnStatus
	if m.Decode(&native) != nil || s.spawns == nil || m.Session != s.registry.Session ||
		m.Revision != s.registry.Revision {
		s.ack(p, m, false, "invalid_spawn_status")
		return
	}
	var err error
	switch native.State {
	case "created":
		if s.actors == nil {
			err = errors.New("missing_actor_registry")
		} else {
			actor, ok := s.actors.Lookup(native.ActorID)
			if !ok || actor.State == world.ActorRemoved {
				err = errors.New("unregistered_native_actor")
			} else {
				err = s.spawns.Created(native.RequestID, native.Index, native.ActorID, native.X, native.Y)
			}
		}
	case "failed":
		err = s.spawns.Fail(native.RequestID, native.Index, native.Reason)
	case "uncertain":
		if s.spawns.Active != native.RequestID {
			err = errors.New("unexpected_uncertain_spawn")
		} else if status, ok := s.spawns.Lookup(native.RequestID); !ok || native.Index < 0 ||
			native.Index >= len(status.Units) || status.Units[native.Index].State == "ready" {
			err = errors.New("unknown_uncertain_spawn")
		} else if status.Units[native.Index].State != "uncertain" {
			_, _ = s.spawns.Uncertain()
		}
	case "not_received":
		err = s.spawns.NotReceived(native.RequestID, native.Index)
	default:
		err = errors.New("invalid_spawn_state")
	}
	if err != nil {
		s.ack(p, m, false, err.Error())
		return
	}
	s.saveSpawns()
	s.ack(p, m, true, "")
	status, _ := s.spawns.Lookup(native.RequestID)
	s.spawnStatus(status)
	if native.State == "created" && s.actors.Commandable(native.ActorID) {
		s.spawnActorReady(native.ActorID)
	} else if native.State == "failed" || native.State == "not_received" {
		s.pumpSpawns()
	}
}

func (s *service) spawnActorReady(actorID string) {
	if s.spawns == nil || !s.actors.Commandable(actorID) {
		return
	}
	id, index, ok := s.spawns.FindActor(actorID)
	if !ok {
		return
	}
	if err := s.spawns.Ready(id, index, actorID); err != nil {
		return
	}
	s.saveSpawns()
	status, _ := s.spawns.Lookup(id)
	s.spawnStatus(status)
	s.pumpSpawns()
}
