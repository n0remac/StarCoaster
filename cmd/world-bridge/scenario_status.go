package main

import (
	"encoding/json"
)

type scenarioStatus struct {
	Session                string  `json:"session"`
	ScenarioID             string  `json:"scenario_id"`
	DisplayName            string  `json:"display_name"`
	Mode                   string  `json:"mode"`
	Objective              string  `json:"objective"`
	WaveOrdinal            int     `json:"wave_ordinal"`
	WaveTotal              int     `json:"wave_total"`
	WaveState              string  `json:"wave_state"`
	Outcome                string  `json:"outcome"`
	Error                  string  `json:"error"`
	TotalTriggered         int     `json:"total_triggered"`
	NextWaveSeconds        int     `json:"next_wave_seconds"`
	ActiveZerglings        int     `json:"active_zerglings"`
	ActiveEnemies          int     `json:"active_enemies"`
	ManualCooldownSeconds  int     `json:"manual_cooldown_seconds"`
	ManualEligible         bool    `json:"manual_eligible"`
	DefenseEnabled         bool    `json:"defense_enabled,omitempty"`
	SpawnAnchor            *[2]int `json:"spawn_anchor,omitempty"`
	WaveIntervalSeconds    int     `json:"wave_interval_seconds,omitempty"`
	WaveDifficulty         string  `json:"wave_difficulty,omitempty"`
	UnlimitedResources     bool    `json:"unlimited_resources,omitempty"`
	FiniteEconomy          bool    `json:"finite_economy,omitempty"`
	EconomyBootstrap       string  `json:"economy_bootstrap,omitempty"`
	EconomyBlockedReason   string  `json:"economy_blocked_reason,omitempty"`
	EnemyBaseBootstrap     string  `json:"enemy_base_bootstrap,omitempty"`
	EnemyBaseBlockedReason string  `json:"enemy_base_blocked_reason,omitempty"`
	DefenseConfigurable    bool    `json:"defense_configurable,omitempty"`
	AutomaticPerimeter     bool    `json:"automatic_perimeter,omitempty"`
	BaseProduction         bool    `json:"base_production,omitempty"`
	EnemyProductionState   string  `json:"enemy_production_state,omitempty"`
	EnemyMinerals          int     `json:"enemy_minerals,omitempty"`
	EnemySupplyUsed        int     `json:"enemy_supply_used,omitempty"`
	EnemySupplyTotal       int     `json:"enemy_supply_total,omitempty"`
	EnemyLarvae            int     `json:"enemy_larvae,omitempty"`
	EnemyEggs              int     `json:"enemy_eggs,omitempty"`
	EnemyGarrison          int     `json:"enemy_garrison,omitempty"`
	EnemyTrainOrders       int     `json:"enemy_train_orders,omitempty"`
	EnemyAttackers         int     `json:"enemy_attackers,omitempty"`
	EnemyWaveShortfall     int     `json:"enemy_wave_shortfall,omitempty"`
}

func (s *service) currentScenarioStatus() scenarioStatus {
	status := scenarioStatus{Session: s.registry.Session, ScenarioID: s.scenario.ID,
		DisplayName: s.scenario.DisplayName, Mode: s.scenario.Mode,
		Outcome: s.outcome, ActiveZerglings: s.lastZerglings, ActiveEnemies: s.lastEnemies}
	status.FiniteEconomy = s.finiteEconomy()
	if status.FiniteEconomy {
		status.EconomyBootstrap = "preparing"
		if s.scenario.Economy.LayoutState == "blocked" {
			status.EconomyBootstrap = "blocked"
			status.EconomyBlockedReason = s.scenario.Economy.BlockedReason
		} else if s.runtime != nil && s.runtime.EconomyReadyFrame > 0 {
			status.EconomyBootstrap = "ready"
		}
	}
	if s.scenario.EnemyBase != nil {
		if s.scenario.EnemyBase.Version == 2 && s.scenario.EnemyBase.LayoutState == "ready" {
			status.EnemyProductionState = s.enemyProductionState
			if s.registry.Destroyed["scenario:enemy-hatchery"] {
				status.EnemyProductionState = "colony_defeated"
			} else if s.registry.Destroyed["scenario:enemy-spawning-pool"] {
				status.EnemyProductionState = "spawning_pool_destroyed"
			}
			if status.EnemyProductionState == "" {
				status.EnemyProductionState = "waiting_for_native_base"
			}
			status.EnemyMinerals = s.enemyProductionMinerals
			status.EnemySupplyUsed = s.enemyProductionSupplyUsed
			status.EnemySupplyTotal = s.enemyProductionSupplyTotal
			status.EnemyLarvae = s.enemyProductionLarvae
			if s.runtime != nil && s.runtime.EnemyProduction != nil {
				status.EnemyTrainOrders = len(s.runtime.EnemyProduction.Orders)
			}
			if s.actors != nil {
				assigned := map[string]bool{}
				if s.runtime != nil && s.runtime.EnemyAssault != nil {
					assigned = s.runtime.EnemyAssault.OrderedIDs()
				}
				for _, actor := range s.actors.Living() {
					if actor.Owner != 0 {
						continue
					}
					switch actor.Type {
					case "zerg_egg":
						status.EnemyEggs++
					case "zerg_zergling":
						if actor.Phase == "complete" {
							if assigned[actor.ID] {
								status.EnemyAttackers++
							} else {
								status.EnemyGarrison++
							}
						}
					}
				}
			}
		}
		status.EnemyBaseBootstrap = "preparing"
		if s.registry.Destroyed["scenario:enemy-hatchery"] {
			status.EnemyBaseBootstrap = "defeated"
		} else if s.scenario.EnemyBase.LayoutState == "blocked" {
			status.EnemyBaseBootstrap = "blocked"
			status.EnemyBaseBlockedReason = s.scenario.EnemyBase.BlockedReason
		} else if s.enemyBaseSession == s.registry.Session &&
			s.enemyBaseRevision == s.registry.Revision {
			if s.enemyBasePublisher && s.enemyBaseController &&
				s.proxies["scenario:enemy-hatchery"] != "" &&
				s.proxies["scenario:enemy-spawning-pool"] != "" {
				status.EnemyBaseBootstrap = "native_validated"
			} else if s.enemyBasePublisher && s.enemyBaseController {
				status.EnemyBaseBootstrap = "blocked"
				status.EnemyBaseBlockedReason = "projection_binding_missing"
			} else if s.enemyBaseReason != "" && s.enemyBaseReason != "native_validation_pending" {
				status.EnemyBaseBootstrap = "blocked"
				status.EnemyBaseBlockedReason = s.enemyBaseReason
			}
		}
	}
	if s.scenario.Mode == "park_defense" {
		status.Objective = "Manage and defend the park"
		status.WaveIntervalSeconds = (s.scenario.ParkDefense.IntervalFrames + 23) / 24
		status.WaveDifficulty = "standard"
		status.UnlimitedResources = s.scenario.UnlimitedResources
		status.DefenseConfigurable = s.scenario.ParkDefense.ManualActivation ||
			s.scenario.ParkDefense.SpawnPolicy == "automatic_perimeter" ||
			s.scenario.ParkDefense.SpawnPolicy == "base_production"
		status.AutomaticPerimeter = s.scenario.ParkDefense.SpawnPolicy == "automatic_perimeter"
		status.BaseProduction = s.scenario.ParkDefense.SpawnPolicy == "base_production"
		if s.runtime != nil {
			status.WaveIntervalSeconds = (s.runtime.IntervalFrames(s.scenario) + 23) / 24
			if s.runtime.WaveDifficulty != "" {
				status.WaveDifficulty = s.runtime.WaveDifficulty
			}
			status.DefenseEnabled = s.runtime.DefenseEnabled
			status.SpawnAnchor = s.runtime.SpawnAnchor
			if status.AutomaticPerimeter && len(s.runtime.Waves) > 0 {
				status.SpawnAnchor = s.runtime.Waves[len(s.runtime.Waves)-1].SpawnAnchor
			}
			status.TotalTriggered = s.runtime.TotalTriggered
			status.WaveOrdinal = s.runtime.TotalTriggered
			status.WaveTotal = 0
			status.NextWaveSeconds = (s.runtime.NextAutomaticFrame - s.runtime.LastFrame + 23) / 24
			if status.AutomaticPerimeter && s.runtime.NextAutomaticFrame == 0 {
				status.NextWaveSeconds = (s.scenario.ParkDefense.InitialDelayFrames + 23) / 24
			}
			if status.NextWaveSeconds < 0 {
				status.NextWaveSeconds = 0
			}
			if !status.DefenseEnabled {
				status.NextWaveSeconds = 0
			}
			if status.FiniteEconomy && status.EconomyBootstrap != "ready" {
				status.NextWaveSeconds = 0
			}
			cooldown := s.scenario.ParkDefense.ManualCooldownFrames - (s.runtime.LastFrame - s.runtime.LastManualFrame)
			if s.runtime.LastManualFrame == 0 || cooldown < 0 {
				cooldown = 0
			}
			status.ManualCooldownSeconds = (cooldown + 23) / 24
			status.ManualEligible = s.scenario.ParkDefense.SpawnPolicy != "automatic_perimeter" &&
				s.scenario.ParkDefense.SpawnPolicy != "base_production" && status.DefenseEnabled &&
				s.ready && s.bw != nil && s.controller != nil && cooldown == 0 && s.runtime.Error == ""
			status.WaveState = "pending"
			if s.scenario.ParkDefense.SpawnPolicy == "base_production" {
				status.WaveState = "base_bootstrap"
				if s.runtime.NextAutomaticFrame > 0 && status.DefenseEnabled &&
					status.EnemyBaseBootstrap != "defeated" {
					status.NextWaveSeconds = max(0, (s.runtime.NextAutomaticFrame-s.runtime.LastFrame+23)/24)
				} else {
					status.NextWaveSeconds = 0
				}
				if s.runtime.EnemyAssault != nil {
					status.WaveOrdinal = len(s.runtime.EnemyAssault.Waves)
					if len(s.runtime.EnemyAssault.Waves) > 0 {
						last := s.runtime.EnemyAssault.Waves[len(s.runtime.EnemyAssault.Waves)-1]
						status.EnemyWaveShortfall = last.Desired - len(last.Actors)
						switch last.State {
						case "pending":
							status.WaveState = "spawning"
						case "ordered":
							status.WaveState = "active"
						case "cleared":
							status.WaveState = "cleared"
						case "route_blocked", "uncertain", "failed":
							status.WaveState = "failed"
						}
						if last.State == "route_blocked" || last.State == "uncertain" {
							status.Error = last.Attempts[len(last.Attempts)-1].Reason
						}
					}
				}
				if status.EnemyBaseBootstrap == "blocked" {
					status.Error = "enemy_base_waiting:" + status.EnemyBaseBlockedReason
				}
			}
			for _, wave := range s.runtime.Waves {
				if wave.State != "cleared" && wave.State != "failed" {
					status.WaveState = wave.State
				}
				if wave.FailureReason != "" {
					status.Error = wave.FailureReason
				}
			}
			if s.runtime.Error != "" {
				status.Error = s.runtime.Error
			}
			if s.scenario.ParkDefense.SpawnPolicy == "automatic_perimeter" && s.perimeterRetryFrame > s.runtime.LastFrame {
				status.Error = "Waves waiting: no reachable edge location"
			}
		}
		return status
	}
	for _, objective := range s.scenario.Objectives {
		if objective.ID == s.scenario.InitialAI.Objective {
			status.Objective = objective.Description
			if status.Objective == "" {
				status.Objective = objective.ID
			}
			break
		}
	}
	if s.runtime != nil {
		status.WaveTotal = len(s.runtime.Waves)
		status.WaveOrdinal = status.WaveTotal
		status.WaveState = "cleared"
		for index, wave := range s.runtime.Waves {
			if wave.State != "cleared" {
				status.WaveOrdinal, status.WaveState = index+1, wave.State
				if wave.FailureReason != "" {
					status.Error = wave.FailureReason
				}
				break
			}
		}
		if s.runtime.Error != "" {
			status.Error = s.runtime.Error
		}
	} else {
		status.WaveTotal = len(s.scenario.SpawnWaves)
		status.WaveOrdinal = status.WaveTotal
		if status.WaveTotal > 0 {
			status.WaveState = "active"
		}
	}
	return status
}

func (s *service) publishScenarioStatus(force bool) {
	if s.scenario == nil || s.registry.Session == "" {
		return
	}
	status := s.currentScenarioStatus()
	data, _ := json.Marshal(status)
	if !force && string(data) == s.lastScenarioStatus {
		return
	}
	if s.emit(s.park, "scenario.status", s.registry.Session, s.registry.Revision, status) == nil {
		s.lastScenarioStatus = string(data)
	}
}
