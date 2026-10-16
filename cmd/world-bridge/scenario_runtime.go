package main

import (
	"encoding/json"
	"fmt"
	"log"
	"os"
	"path/filepath"

	"starcoaster/internal/world"
)

func (s *service) initScenarioRuntime() error {
	if s.scenario == nil || s.scenario.Version != 2 {
		return nil
	}
	session := s.registry.Session
	if s.runtime != nil && s.runtime.Session == session {
		return s.runtime.Validate(s.scenario, session)
	}
	path := s.spawnJournalPath + ".scenario.json"
	if data, err := os.ReadFile(path); err == nil {
		var prior world.ScenarioRuntime
		if err := json.Unmarshal(data, &prior); err != nil {
			return fmt.Errorf("invalid_scenario_journal: %w", err)
		}
		if prior.Session == session {
			if err := prior.Validate(s.scenario, session); err != nil {
				return err
			}
			s.runtime = &prior
			return nil
		}
	} else if !os.IsNotExist(err) {
		return err
	}
	s.runtime = world.NewScenarioRuntime(s.scenario, session)
	if !s.saveScenarioRuntime() {
		return fmt.Errorf("scenario_journal_unavailable")
	}
	return nil
}

func (s *service) saveScenarioRuntime() bool {
	if s.runtime == nil {
		return true
	}
	path := s.spawnJournalPath + ".scenario.json"
	data, err := json.Marshal(s.runtime)
	if err != nil {
		log.Printf("scenario journal encode: %v", err)
		return false
	}
	if err := os.MkdirAll(filepath.Dir(path), 0700); err != nil {
		log.Printf("scenario journal directory: %v", err)
		return false
	}
	temporary := path + ".tmp"
	if err := os.WriteFile(temporary, data, 0600); err != nil {
		log.Printf("scenario journal write: %v", err)
		return false
	}
	if err := os.Rename(temporary, path); err != nil {
		log.Printf("scenario journal replace: %v", err)
		return false
	}
	return true
}

func (s *service) scenarioRuntimeError(err error) {
	if s.runtime != nil {
		s.runtime.Error = err.Error()
		_ = s.saveScenarioRuntime()
	}
	log.Printf("scenario runtime unhealthy: %v", err)
	_ = s.emit(s.park, "world.error", s.registry.Session, s.registry.Revision,
		map[string]string{"reason": err.Error()})
}

func (s *service) advanceScenarioRuntime(frame int, seq uint64, living map[string]bool) {
	r := s.runtime
	if r == nil || r.Outcome != "" || r.Error != "" {
		return
	}
	if s.scenario.Mode == "park_defense" && r.Started && (frame <= r.LastFrame || seq <= r.LastSeq) {
		return // stale native snapshots cannot move the recurring schedule
	}
	if err := r.AcceptFrame(frame, seq, true); err != nil {
		s.scenarioRuntimeError(err)
		return
	}
	removed := map[string]bool{}
	for _, wave := range r.Waves {
		for _, unit := range wave.Units {
			if unit.ActorID == "" || s.actors == nil {
				continue
			}
			if actor, ok := s.actors.Lookup(unit.ActorID); ok && actor.State == world.ActorRemoved {
				removed[unit.ActorID] = true
			} else if s.actorReconcileComplete && !s.reconciledActors[unit.ActorID] {
				// A complete native reconciliation excludes this previously ready
				// actor. Reconcile also requires absence from this complete snapshot.
				removed[unit.ActorID] = true
			}
		}
	}
	r.Reconcile(s.spawns, living, removed)
	r.Trigger(s.scenario)
	pruned := r.PruneParkDefenseHistory(s.scenario)
	if !s.saveScenarioRuntime() {
		s.scenarioRuntimeError(fmt.Errorf("scenario_journal_unavailable"))
		return
	}
	if len(pruned) > 0 && s.spawns.PruneSettled(pruned) > 0 && !s.saveSpawns() {
		s.scenarioRuntimeError(fmt.Errorf("spawn_journal_unavailable"))
		return
	}
	if s.outcome != "" {
		return
	}
	if s.parkPatch != nil || s.targetPatch != nil {
		return
	}
	for {
		// Crash gap: a durable intent may exist without its queue entry. Submit
		// the exact same request ID and coordinates before making a new plan.
		var request world.SpawnRequest
		found := false
		for _, wave := range r.Waves {
			for _, unit := range wave.Units {
				if unit.State != "submitted" || len(unit.Attempts) == 0 {
					continue
				}
				attempt := unit.Attempts[len(unit.Attempts)-1]
				if _, ok := s.spawns.Request(attempt.RequestID); ok {
					continue
				}
				request = world.SpawnRequest{RequestID: attempt.RequestID, UnitType: "zerg_zergling", Count: 1,
					X: attempt.X, Y: attempt.Y, Formation: "compact", PlayerID: 0}
				found = true
				break
			}
			if found {
				break
			}
		}
		if !found {
			wi, ui, ok := r.NextPlanned()
			if !ok {
				break
			}
			unit := &r.Waves[wi].Units[ui]
			zone, valid := r.WaveZone(s.scenario, wi, unit.GroupIndex)
			if !valid {
				s.scenarioRuntimeError(fmt.Errorf("scenario_wave_template_missing"))
				return
			}
			excluded := make([]world.Point, 0, len(unit.Attempts))
			for _, attempt := range unit.Attempts {
				excluded = append(excluded, world.Point{X: attempt.X, Y: attempt.Y})
			}
			position, ok := s.scenarioZoneCandidate(zone, excluded)
			if !ok {
				if s.scenario.Mode == "park_defense" {
					r.Waves[wi].FailureReason = "no_eligible_spawn_zone_tile"
					break
				}
				unit.State = "failed"
				r.Waves[wi].FailureReason = "no_eligible_spawn_zone_tile"
				if !s.saveScenarioRuntime() {
					s.scenarioRuntimeError(fmt.Errorf("scenario_journal_unavailable"))
					return
				}
				continue
			}
			if s.spawns.PendingCount() >= 64 || s.lastMarines+s.lastZerglings+s.spawns.PendingCount()+1 > s.actorLimit() {
				break
			}
			r.Waves[wi].FailureReason = ""
			request = r.Intent(wi, ui, position)
			if !s.saveScenarioRuntime() {
				s.scenarioRuntimeError(fmt.Errorf("scenario_journal_unavailable"))
				return
			}
		}
		if s.spawns.PendingCount() >= 64 || s.lastMarines+s.lastZerglings+s.spawns.PendingCount()+1 > s.actorLimit() {
			break
		}
		status, err := s.spawns.Submit(s.registry.Session, request)
		if err != nil {
			if err.Error() == "spawn_queue_full" {
				break
			}
			s.scenarioRuntimeError(err)
			return
		}
		if !s.saveSpawns() {
			s.scenarioRuntimeError(fmt.Errorf("spawn_journal_unavailable"))
			return
		}
		if !s.saveScenarioRuntime() {
			s.scenarioRuntimeError(fmt.Errorf("scenario_journal_unavailable"))
			return
		}
		log.Printf("scenario spawn request=%s wave=%s state=%s", request.RequestID,
			s.scenarioWaveForRequest(request.RequestID), status.State)
	}
	r.Reconcile(s.spawns, living, removed)
	r.Trigger(s.scenario)
	if !s.saveScenarioRuntime() {
		s.scenarioRuntimeError(fmt.Errorf("scenario_journal_unavailable"))
		return
	}
	s.pumpSpawns()
}

func (s *service) actorLimit() int {
	if s.maxLiveActors < 1 || s.maxLiveActors > 256 {
		return 240
	}
	return s.maxLiveActors
}
