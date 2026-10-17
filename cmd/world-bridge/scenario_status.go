package main

import (
	"encoding/json"
)

type scenarioStatus struct {
	Session               string `json:"session"`
	ScenarioID            string `json:"scenario_id"`
	DisplayName           string `json:"display_name"`
	Mode                  string `json:"mode"`
	Objective             string `json:"objective"`
	WaveOrdinal           int    `json:"wave_ordinal"`
	WaveTotal             int    `json:"wave_total"`
	WaveState             string `json:"wave_state"`
	Outcome               string `json:"outcome"`
	Error                 string `json:"error"`
	TotalTriggered        int    `json:"total_triggered"`
	NextWaveSeconds       int    `json:"next_wave_seconds"`
	ActiveZerglings       int    `json:"active_zerglings"`
	ActiveEnemies         int    `json:"active_enemies"`
	ManualCooldownSeconds int    `json:"manual_cooldown_seconds"`
	ManualEligible        bool   `json:"manual_eligible"`
}

func (s *service) currentScenarioStatus() scenarioStatus {
	status := scenarioStatus{Session: s.registry.Session, ScenarioID: s.scenario.ID,
		DisplayName: s.scenario.DisplayName, Mode: s.scenario.Mode,
		Outcome: s.outcome, ActiveZerglings: s.lastZerglings, ActiveEnemies: s.lastEnemies}
	if s.scenario.Mode == "park_defense" {
		status.Objective = "Manage and defend the park"
		if s.runtime != nil {
			status.TotalTriggered = s.runtime.TotalTriggered
			status.WaveOrdinal = s.runtime.TotalTriggered
			status.WaveTotal = 0
			status.NextWaveSeconds = (s.runtime.NextAutomaticFrame - s.runtime.LastFrame + 23) / 24
			if status.NextWaveSeconds < 0 {
				status.NextWaveSeconds = 0
			}
			cooldown := s.scenario.ParkDefense.ManualCooldownFrames - (s.runtime.LastFrame - s.runtime.LastManualFrame)
			if s.runtime.LastManualFrame == 0 || cooldown < 0 {
				cooldown = 0
			}
			status.ManualCooldownSeconds = (cooldown + 23) / 24
			status.ManualEligible = s.ready && s.bw != nil && s.controller != nil && cooldown == 0 && s.runtime.Error == ""
			status.WaveState = "pending"
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
