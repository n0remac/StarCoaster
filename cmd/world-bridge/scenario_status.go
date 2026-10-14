package main

import (
	"encoding/json"
)

type scenarioStatus struct {
	Session     string `json:"session"`
	ScenarioID  string `json:"scenario_id"`
	DisplayName string `json:"display_name"`
	Objective   string `json:"objective"`
	WaveOrdinal int    `json:"wave_ordinal"`
	WaveTotal   int    `json:"wave_total"`
	WaveState   string `json:"wave_state"`
	Outcome     string `json:"outcome"`
	Error       string `json:"error"`
}

func (s *service) currentScenarioStatus() scenarioStatus {
	status := scenarioStatus{Session: s.registry.Session, ScenarioID: s.scenario.ID,
		DisplayName: s.scenario.DisplayName, Outcome: s.outcome}
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
