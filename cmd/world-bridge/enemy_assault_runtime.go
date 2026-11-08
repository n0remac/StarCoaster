package main

import (
	"fmt"
	"log"
	"strconv"

	"starcoaster/internal/world"
)

type enemyAssaultReceipt struct {
	RequestID string `json:"request_id"`
	WaveID    string `json:"wave_id"`
	Accepted  bool   `json:"accepted"`
	Reason    string `json:"reason"`
	Frame     int    `json:"frame"`
	Assigned  int    `json:"assigned"`
}

func (s *service) sendEnemyAssault(wave *world.EnemyAssaultWave, attempt *world.EnemyAssaultAttempt) {
	if s.bw == nil || wave == nil || attempt == nil {
		return
	}
	actors := make([]map[string]any, 0, len(attempt.ActorIDs))
	for _, id := range attempt.ActorIDs {
		for _, actor := range wave.Actors {
			if actor.ID == id {
				actors = append(actors, map[string]any{"id": actor.ID,
					"native_id": actor.NativeID, "generation": actor.Generation})
				break
			}
		}
	}
	payload := map[string]any{"request_id": attempt.RequestID, "wave_id": wave.ID,
		"source_base_id": wave.SourceBaseID, "source_native_id": wave.SourceNativeID,
		"destination_x": wave.Destination[0], "destination_y": wave.Destination[1],
		"actors": actors}
	if err := s.emit(s.bw, "scenario.enemy_assault.assign", s.registry.Session,
		s.registry.Revision, payload); err != nil {
		log.Printf("enemy assault send uncertain request=%s: %v", attempt.RequestID, err)
	}
	log.Printf("enemy assault intent request=%s wave=%s actors=%d desired=%d frame=%d revision=%d",
		attempt.RequestID, wave.ID, len(actors), wave.Desired, attempt.Frame, attempt.Revision)
}

func (s *service) queryPendingEnemyAssault(frame int) bool {
	if s.runtime == nil || s.runtime.EnemyAssault == nil {
		return false
	}
	wave, attempt := s.runtime.EnemyAssault.Pending()
	if attempt == nil {
		return false
	}
	if s.bw == nil || !s.ready || frame < attempt.Frame+120 ||
		frame < s.enemyAssaultQueryFrame {
		return true
	}
	payload := map[string]any{"request_id": attempt.RequestID, "wave_id": wave.ID}
	if err := s.emit(s.bw, "scenario.enemy_assault.query", s.registry.Session,
		s.registry.Revision, payload); err != nil {
		log.Printf("enemy assault receipt query: %v", err)
		return true
	}
	s.enemyAssaultQueryFrame = frame + 240
	return true
}

func (s *service) advanceEnemyAssault(frame int, living map[string]bool) {
	if s.scenario == nil || s.scenario.ParkDefense == nil ||
		s.scenario.ParkDefense.SpawnPolicy != "base_production" ||
		s.scenario.EnemyBase == nil || s.scenario.EnemyBase.Version != 2 ||
		s.runtime == nil || s.runtime.EnemyAssault == nil {
		return
	}
	r, ledger := s.runtime, s.runtime.EnemyAssault
	dead := map[string]bool{}
	for _, wave := range ledger.Waves {
		for _, actor := range wave.Actors {
			if !living[actor.ID] {
				dead[actor.ID] = true
			}
			if s.actors != nil {
				if record, ok := s.actors.Lookup(actor.ID); ok && record.State == world.ActorRemoved {
					dead[actor.ID] = true
				}
			}
		}
	}
	if ledger.MarkDead(dead) && !s.saveScenarioRuntime() {
		s.scenarioRuntimeError(fmt.Errorf("scenario_journal_unavailable"))
		return
	}
	if s.queryPendingEnemyAssault(frame) {
		return
	}
	for wi := range ledger.Waves {
		wave := &ledger.Waves[wi]
		if wave.State == "uncertain" {
			return
		}
		if wave.State != "route_blocked" {
			continue
		}
		if !r.DefenseEnabled || s.registry.Destroyed["scenario:enemy-hatchery"] {
			return
		}
		if len(wave.Attempts) >= 3 {
			return
		}
		if s.parkPatch != nil || s.targetPatch != nil || !s.ready {
			return
		}
		attempt, ok := ledger.Retry(s.registry.Session, wave.Sequence, frame, s.registry.Revision)
		if !ok {
			return
		}
		if !s.saveScenarioRuntime() {
			s.scenarioRuntimeError(fmt.Errorf("scenario_journal_unavailable"))
			return
		}
		s.sendEnemyAssault(wave, &attempt)
		return
	}
	if !r.DefenseEnabled || !s.ready || s.bw == nil || s.controller == nil ||
		s.parkPatch != nil || s.targetPatch != nil || r.Error != "" || r.Outcome != "" ||
		r.EconomyReadyFrame == 0 || !s.actorReconcileComplete ||
		s.registry.Destroyed["scenario:enemy-hatchery"] || ledger.ColonyNativeID < 1 ||
		s.scenario.EnemyBase.LayoutState != "ready" {
		return
	}
	if r.NextAutomaticFrame == 0 {
		r.NextAutomaticFrame = r.EconomyReadyFrame + s.scenario.ParkDefense.InitialDelayFrames
		return
	}
	if frame < r.NextAutomaticFrame {
		return
	}
	assigned := ledger.AssignedIDs()
	candidates := make([]world.EnemyAssaultActor, 0, 12)
	if s.actors != nil {
		for _, identity := range s.actors.Living() {
			if identity.Type != "zerg_zergling" || identity.Phase != "complete" ||
				identity.Owner != 0 || !living[identity.ID] || assigned[identity.ID] ||
				!s.actors.Commandable(identity.ID) {
				continue
			}
			record, _ := s.actors.Lookup(identity.ID)
			binding, ok := record.Bindings["publisher"]
			if !ok || record.Bindings["controller"].NativeID == "" {
				continue
			}
			nativeID, err := strconv.Atoi(binding.NativeID)
			if err != nil || nativeID < 1 {
				continue
			}
			candidates = append(candidates, world.EnemyAssaultActor{ID: identity.ID,
				Generation: identity.Generation, NativeID: nativeID,
				Type: identity.Type, State: "alive"})
		}
	}
	if len(candidates) == 0 {
		// No backlog: inspect again at a bounded native cadence while production
		// can continue, or wait one full interval after the finite bank ends.
		if s.enemyProductionState == "production_exhausted" {
			r.NextAutomaticFrame = frame + r.IntervalFrames(s.scenario)
		} else {
			r.NextAutomaticFrame = frame + 240
		}
		return
	}
	sequence := len(ledger.Waves) + 1
	desired := r.DesiredBaseWaveSize(s.scenario, sequence)
	if desired < 1 {
		s.scenarioRuntimeError(fmt.Errorf("base_wave_composition_invalid"))
		return
	}
	base := s.scenario.EnemyBase
	goal := [2]int{s.transform.X(base.TerranApproachTile[0]*32 + 16),
		s.transform.Y(base.TerranApproachTile[1]*32 + 16)}
	wave, ok := ledger.Commit(s.registry.Session, sequence, frame, s.registry.Revision,
		ledger.ColonyNativeID, goal, desired, candidates)
	if !ok {
		s.scenarioRuntimeError(fmt.Errorf("base_wave_commit_invalid"))
		return
	}
	r.TotalTriggered++
	r.NextWaveSequence = sequence + 1
	r.NextAutomaticFrame = frame + r.IntervalFrames(s.scenario)
	if !s.saveScenarioRuntime() {
		s.scenarioRuntimeError(fmt.Errorf("scenario_journal_unavailable"))
		return
	}
	s.sendEnemyAssault(&wave, &wave.Attempts[0])
	s.publishScenarioStatus(false)
}

func (s *service) recordEnemyAssaultReceipt(receipt enemyAssaultReceipt) {
	if s.runtime == nil || s.runtime.EnemyAssault == nil {
		return
	}
	wave, attempt := s.runtime.EnemyAssault.Pending()
	if attempt == nil || attempt.RequestID != receipt.RequestID || wave.ID != receipt.WaveID ||
		receipt.Frame < attempt.Frame || receipt.Assigned != 0 && !receipt.Accepted ||
		receipt.Accepted && receipt.Assigned != len(attempt.ActorIDs) {
		return
	}
	if !s.runtime.EnemyAssault.Resolve(receipt.RequestID, receipt.Accepted, receipt.Reason, receipt.Frame) {
		return
	}
	if !s.saveScenarioRuntime() {
		s.scenarioRuntimeError(fmt.Errorf("scenario_journal_unavailable"))
		return
	}
	log.Printf("enemy assault receipt request=%s wave=%s accepted=%t reason=%s assigned=%d frame=%d",
		receipt.RequestID, receipt.WaveID, receipt.Accepted, receipt.Reason, receipt.Assigned, receipt.Frame)
	s.publishScenarioStatus(false)
}

func (s *service) handleEnemyAssaultReceipt(p *peer, m world.Envelope) {
	var receipt enemyAssaultReceipt
	if p != s.bw || m.Session != s.registry.Session || m.Revision != s.registry.Revision ||
		m.Decode(&receipt) != nil {
		s.ack(p, m, false, "invalid_enemy_assault_receipt")
		return
	}
	s.ack(p, m, true, "")
	s.recordEnemyAssaultReceipt(receipt)
}

func (s *service) handleEnemyAssaultResult(p *peer, m world.Envelope) {
	var result struct {
		RequestID string               `json:"request_id"`
		Found     bool                 `json:"found"`
		Receipt   *enemyAssaultReceipt `json:"receipt"`
	}
	if p != s.bw || m.Session != s.registry.Session || m.Revision != s.registry.Revision ||
		m.Decode(&result) != nil || s.runtime == nil || s.runtime.EnemyAssault == nil {
		s.ack(p, m, false, "invalid_enemy_assault_result")
		return
	}
	wave, attempt := s.runtime.EnemyAssault.Pending()
	if attempt == nil || attempt.RequestID != result.RequestID {
		s.ack(p, m, false, "stale_enemy_assault_result")
		return
	}
	s.ack(p, m, true, "")
	if result.Found && result.Receipt != nil {
		s.recordEnemyAssaultReceipt(*result.Receipt)
	} else {
		s.runtime.EnemyAssault.MarkUncertain(attempt.RequestID)
		if !s.saveScenarioRuntime() {
			s.scenarioRuntimeError(fmt.Errorf("scenario_journal_unavailable"))
			return
		}
		log.Printf("enemy assault uncertain wave=%s request=%s native_receipt_missing", wave.ID, attempt.RequestID)
		s.publishScenarioStatus(false)
	}
}
