package main

import (
	"fmt"
	"log"

	"starcoaster/internal/world"
)

type enemyTrainReceipt struct {
	RequestID        string `json:"request_id"`
	Sequence         int    `json:"sequence"`
	Accepted         bool   `json:"accepted"`
	Reason           string `json:"reason"`
	HatcheryNativeID int    `json:"hatchery_native_id"`
	Frame            int    `json:"frame"`
	MineralsBefore   int    `json:"minerals_before"`
	MineralsAfter    int    `json:"minerals_after"`
}

func (s *service) queryEnemyProduction(frame int) {
	if s.scenario == nil || s.scenario.EnemyBase == nil ||
		s.scenario.EnemyBase.Version != 2 || s.scenario.EnemyBase.LayoutState != "ready" ||
		s.runtime == nil || s.runtime.EnemyProduction == nil || !s.ready || s.bw == nil ||
		!s.enemyBasePublisher || !s.enemyBaseController || s.enemyBasePublisherNativeID < 1 ||
		s.proxies["scenario:enemy-hatchery"] == "" ||
		s.registry.Destroyed["scenario:enemy-hatchery"] ||
		(frame > 0 && frame < s.enemyProductionQueryFrame) {
		return
	}
	id := fmt.Sprintf("enemy-production:%s:%d:%d", s.registry.Session, s.registry.Revision, frame)
	pending := ""
	if order := s.runtime.EnemyProduction.Pending(); order != nil {
		pending = order.RequestID
	}
	payload := map[string]any{"query_id": id, "target_id": "scenario:enemy-hatchery",
		"hatchery_native_id": s.enemyBasePublisherNativeID, "pending_request_id": pending}
	if err := s.emit(s.bw, "scenario.enemy_production.query", s.registry.Session,
		s.registry.Revision, payload); err != nil {
		log.Printf("enemy production query: %v", err)
		return
	}
	s.enemyProductionQueryID = id
	s.enemyProductionQueryFrame = frame + 120
}

func (s *service) recordEnemyTrainReceipt(receipt enemyTrainReceipt) {
	if s.runtime == nil || s.runtime.EnemyProduction == nil {
		return
	}
	order := s.runtime.EnemyProduction.Pending()
	if order == nil || order.RequestID != receipt.RequestID ||
		order.Sequence != receipt.Sequence || order.HatcheryNativeID != receipt.HatcheryNativeID {
		return
	}
	if receipt.Accepted && receipt.MineralsBefore-receipt.MineralsAfter != 50 {
		s.runtime.EnemyProduction.MarkUncertain(receipt.RequestID)
		s.enemyProductionState = "native_spend_unproven"
	} else if s.runtime.EnemyProduction.Resolve(receipt.RequestID, receipt.Accepted, receipt.Reason,
		receipt.Frame, receipt.MineralsBefore, receipt.MineralsAfter) {
		if receipt.Accepted {
			s.enemyProductionState = "training"
		} else {
			s.enemyProductionState = receipt.Reason
		}
	}
	if !s.saveScenarioRuntime() {
		s.scenarioRuntimeError(fmt.Errorf("scenario_journal_unavailable"))
	}
	log.Printf("enemy production receipt request=%s accepted=%t reason=%s minerals=%d->%d frame=%d",
		receipt.RequestID, receipt.Accepted, receipt.Reason, receipt.MineralsBefore,
		receipt.MineralsAfter, receipt.Frame)
	s.publishScenarioStatus(false)
}

func (s *service) handleEnemyProductionReceipt(p *peer, m world.Envelope) {
	var receipt enemyTrainReceipt
	if p != s.bw || m.Session != s.registry.Session || m.Revision != s.registry.Revision ||
		m.Decode(&receipt) != nil {
		s.ack(p, m, false, "invalid_enemy_production_receipt")
		return
	}
	s.ack(p, m, true, "")
	s.recordEnemyTrainReceipt(receipt)
}

func (s *service) handleEnemyProductionResult(p *peer, m world.Envelope) {
	var result struct {
		QueryID          string             `json:"query_id"`
		HatcheryNativeID int                `json:"hatchery_native_id"`
		Present          bool               `json:"present"`
		Minerals         int                `json:"minerals"`
		SupplyUsed       int                `json:"supply_used"`
		SupplyTotal      int                `json:"supply_total"`
		CanTrain         bool               `json:"can_train"`
		PoolComplete     bool               `json:"pool_complete"`
		Larvae           int                `json:"larvae"`
		Receipt          *enemyTrainReceipt `json:"receipt"`
	}
	if p != s.bw || m.Session != s.registry.Session || m.Revision != s.registry.Revision ||
		m.Decode(&result) != nil || result.QueryID != s.enemyProductionQueryID ||
		s.runtime == nil || s.runtime.EnemyProduction == nil ||
		result.Minerals < 0 || result.SupplyUsed < 0 || result.SupplyTotal < 0 {
		s.ack(p, m, false, "invalid_enemy_production_result")
		return
	}
	s.ack(p, m, true, "")
	s.enemyProductionMinerals, s.enemyProductionSupplyUsed = result.Minerals, result.SupplyUsed
	s.enemyProductionSupplyTotal, s.enemyProductionLarvae = result.SupplyTotal, result.Larvae
	if order := s.runtime.EnemyProduction.Pending(); order != nil {
		if result.Receipt == nil || result.Receipt.RequestID != order.RequestID {
			s.runtime.EnemyProduction.MarkUncertain(order.RequestID)
			s.enemyProductionState = "native_receipt_missing"
			if !s.saveScenarioRuntime() {
				s.scenarioRuntimeError(fmt.Errorf("scenario_journal_unavailable"))
			}
		} else {
			s.recordEnemyTrainReceipt(*result.Receipt)
		}
		s.publishScenarioStatus(false)
		return
	}
	if orders := s.runtime.EnemyProduction.Orders; len(orders) > 0 {
		last := orders[len(orders)-1]
		if last.State == "uncertain" || last.State == "rejected" {
			s.enemyProductionState = last.Reason
			s.publishScenarioStatus(false)
			return
		}
	}
	base := s.scenario.EnemyBase
	if !result.Present || result.HatcheryNativeID != s.enemyBasePublisherNativeID {
		s.enemyProductionState = "hatchery_unavailable"
	} else if result.SupplyTotal < base.MinimumSupply {
		s.enemyProductionState = "native_supply_unproven"
	} else if !result.PoolComplete {
		s.enemyProductionState = "spawning_pool_missing"
	} else if len(s.runtime.EnemyProduction.Orders) >= base.MaxTrainOrders || result.Minerals < 50 {
		s.enemyProductionState = "production_exhausted"
	} else if result.SupplyTotal-result.SupplyUsed < 2 {
		s.enemyProductionState = "supply_exhausted"
	} else if result.Larvae == 0 {
		s.enemyProductionState = "larva_pending"
	} else if !result.CanTrain {
		s.enemyProductionState = "native_train_unavailable"
	} else if s.ready && s.parkPatch == nil && s.targetPatch == nil &&
		s.runtime.Error == "" && s.runtime.Outcome == "" {
		order, ok := s.runtime.EnemyProduction.Plan(s.registry.Session, m.BWTick,
			s.enemyBasePublisherNativeID)
		if ok {
			if !s.saveScenarioRuntime() {
				s.scenarioRuntimeError(fmt.Errorf("scenario_journal_unavailable"))
				return
			}
			payload := map[string]any{"request_id": order.RequestID,
				"sequence": order.Sequence, "target_id": "scenario:enemy-hatchery",
				"target_proxy_id":    s.proxies["scenario:enemy-hatchery"],
				"hatchery_native_id": order.HatcheryNativeID, "unit_type": "zerg_zergling"}
			if err := s.emit(s.bw, "scenario.enemy_production.train", s.registry.Session,
				s.registry.Revision, payload); err != nil {
				log.Printf("enemy production send uncertain request=%s: %v", order.RequestID, err)
			}
			s.enemyProductionState = "train_pending"
			log.Printf("enemy production intent request=%s hatchery=%d frame=%d", order.RequestID,
				order.HatcheryNativeID, m.BWTick)
		}
	}
	s.publishScenarioStatus(false)
}
