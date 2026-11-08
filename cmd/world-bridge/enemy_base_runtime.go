package main

import (
	"fmt"
	"log"

	"starcoaster/internal/world"
)

// The read-only query is repeated after native reconnection or a confirmed
// geometry revision. It never initializes or restores a destroyed base.
func (s *service) queryEnemyBase(frame int) {
	if s.scenario == nil || s.scenario.EnemyBase == nil ||
		s.scenario.EnemyBase.LayoutState != "ready" || !s.ready || s.bw == nil || s.controller == nil {
		return
	}
	if s.enemyBaseSession != s.registry.Session || s.enemyBaseRevision != s.registry.Revision {
		s.enemyBaseSession, s.enemyBaseRevision = s.registry.Session, s.registry.Revision
		s.enemyBasePublisher, s.enemyBaseController = false, false
		s.enemyBaseReason = "native_validation_pending"
		s.enemyBaseRetryFrame = 0
		s.enemyBasePublisherNativeID = 0
		s.enemyProductionQueryFrame = 0
	}
	if frame == 0 {
		s.enemyBasePublisher, s.enemyBaseController = false, false
		s.enemyBaseReason = "native_validation_pending"
	}
	if s.enemyBasePublisher && s.enemyBaseController ||
		(frame > 0 && frame < s.enemyBaseRetryFrame) {
		return
	}
	base := s.scenario.EnemyBase
	toNative := func(tile []int) [2]int {
		return [2]int{s.transform.TileX(tile[0]), s.transform.TileY(tile[1])}
	}
	id := fmt.Sprintf("enemy-base:%s:%d", s.registry.Session, s.registry.Revision)
	payload := map[string]any{"query_id": id,
		"hatchery": toNative(base.Structures[0].Tile[:]),
		"pool":     toNative(base.Structures[1].Tile[:]),
		"supply":   toNative(base.SupplyTile), "assembly": toNative(base.AssemblyTile),
		"terran_approach": toNative(base.TerranApproachTile)}
	for _, participant := range []*peer{s.bw, s.controller} {
		if err := participant.send(world.Message("scenario.enemy_base.query", s.registry.Session,
			id, "bridge", s.registry.Revision, payload)); err != nil {
			log.Printf("enemy base native query send: %v", err)
		}
	}
	s.enemyBaseRetryFrame = frame + 240
}

func (s *service) acceptEnemyBaseResult(p *peer, id string, accepted bool, reason string,
	hatchery, pool, overlord int) {
	expected := fmt.Sprintf("enemy-base:%s:%d", s.registry.Session, s.registry.Revision)
	if s.scenario == nil || s.scenario.EnemyBase == nil || id != expected ||
		s.enemyBaseSession != s.registry.Session || s.enemyBaseRevision != s.registry.Revision ||
		(p != s.bw && p != s.controller) {
		return
	}
	if accepted && hatchery > 0 && pool > 0 && overlord > 0 &&
		hatchery != pool && hatchery != overlord && pool != overlord {
		if p == s.bw {
			if s.runtime != nil && s.runtime.EnemyAssault != nil &&
				!s.runtime.EnemyAssault.BindColony(hatchery) {
				s.enemyBaseReason = "native_colony_identity_changed"
				s.publishScenarioStatus(false)
				return
			}
			s.enemyBasePublisher = true
			s.enemyBasePublisherNativeID = hatchery
			if s.runtime != nil && s.runtime.EnemyAssault != nil && !s.saveScenarioRuntime() {
				s.scenarioRuntimeError(fmt.Errorf("scenario_journal_unavailable"))
				return
			}
		} else {
			s.enemyBaseController = true
		}
		if s.enemyBasePublisher && s.enemyBaseController {
			s.enemyBaseReason = ""
		}
		log.Printf("enemy base native role=%s accepted=true hatchery=%d pool=%d overlord=%d revision=%d",
			map[bool]string{true: "publisher", false: "controller"}[p == s.bw],
			hatchery, pool, overlord, s.registry.Revision)
	} else {
		if reason == "" {
			reason = "native_validation_failed"
		}
		s.enemyBaseReason = reason
		log.Printf("enemy base native role=%s accepted=false reason=%s revision=%d",
			map[bool]string{true: "publisher", false: "controller"}[p == s.bw], reason, s.registry.Revision)
	}
	s.publishScenarioStatus(false)
}

func (s *service) handleEnemyBaseResult(p *peer, m world.Envelope) {
	var result struct {
		QueryID          string `json:"query_id"`
		Accepted         bool   `json:"accepted"`
		Reason           string `json:"reason"`
		HatcheryNativeID int    `json:"hatchery_native_id"`
		PoolNativeID     int    `json:"pool_native_id"`
		OverlordNativeID int    `json:"overlord_native_id"`
	}
	if m.Session != s.registry.Session || m.Revision != s.registry.Revision || m.Decode(&result) != nil {
		s.ack(p, m, false, "invalid_enemy_base_result")
		return
	}
	s.ack(p, m, true, "")
	s.acceptEnemyBaseResult(p, result.QueryID, result.Accepted, result.Reason,
		result.HatcheryNativeID, result.PoolNativeID, result.OverlordNativeID)
}
