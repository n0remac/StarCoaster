package world

import (
	"encoding/json"
	"fmt"
	"os"
)

// Scenario supplies the small amount of game-specific state needed by the
// bridge. Park objects are still discovered from the authoritative snapshot.
type Scenario struct {
	Version       int    `json:"version"`
	ID            string `json:"scenario_id"`
	DisplayName   string `json:"display_name"`
	ParkFile      string `json:"park_file"`
	ParkSize      [2]int `json:"park_size"`
	StartingUnits struct {
		Marines   [][2]int `json:"marines"`
		Zerglings [][2]int `json:"zerglings"`
	} `json:"starting_units"`
	Objectives []struct {
		ID         string `json:"id"`
		EntityKind string `json:"entity_kind"`
		EntityType string `json:"entity_type"`
		Required   bool   `json:"required"`
	} `json:"objectives"`
	InitialAI struct {
		Strategy    string `json:"strategy"`
		Objective   string `json:"objective"`
		DelayFrames int    `json:"delay_frames"`
	} `json:"initial_ai"`
	Victory struct {
		AllZerglingsEliminated bool   `json:"all_zerglings_eliminated"`
		ObjectiveIntact        string `json:"objective_intact"`
	} `json:"victory"`
	Defeat struct {
		ObjectiveDestroyed   string `json:"objective_destroyed"`
		AllMarinesEliminated bool   `json:"all_marines_eliminated"`
	} `json:"defeat"`
	SpawnWaves []SpawnWave `json:"spawn_waves,omitempty"`
}

// SpawnWave is a small trusted scenario request, not a player action.
type SpawnWave struct {
	ID        string `json:"id"`
	Trigger   string `json:"trigger"`
	UnitType  string `json:"unit_type"`
	Count     int    `json:"count"`
	X         int    `json:"x"`
	Y         int    `json:"y"`
	Formation string `json:"formation"`
}

func LoadScenario(path string) (*Scenario, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var scenario Scenario
	if err := json.Unmarshal(data, &scenario); err != nil {
		return nil, err
	}
	if scenario.Version != 1 || !identifier.MatchString(scenario.ID) || scenario.ParkSize[0] < 1 || scenario.ParkSize[1] < 1 ||
		scenario.ParkSize[0] > 128 || scenario.ParkSize[1] > 128 || len(scenario.StartingUnits.Marines) == 0 ||
		len(scenario.StartingUnits.Zerglings) == 0 || len(scenario.Objectives) == 0 ||
		scenario.InitialAI.Strategy != "objective_assault" || scenario.InitialAI.Objective == "" ||
		scenario.InitialAI.DelayFrames < 0 || scenario.InitialAI.DelayFrames > 600 ||
		!scenario.Victory.AllZerglingsEliminated || !scenario.Defeat.AllMarinesEliminated ||
		scenario.Victory.ObjectiveIntact != scenario.InitialAI.Objective ||
		scenario.Defeat.ObjectiveDestroyed != scenario.InitialAI.Objective {
		return nil, fmt.Errorf("invalid scenario configuration")
	}
	for _, objective := range scenario.Objectives {
		if !identifier.MatchString(objective.ID) || objective.EntityKind == "" || objective.EntityType == "" {
			return nil, fmt.Errorf("invalid scenario objective")
		}
	}
	if len(scenario.SpawnWaves) > 4 {
		return nil, fmt.Errorf("too many scenario spawn waves")
	}
	seenWave := map[string]bool{}
	for _, wave := range scenario.SpawnWaves {
		if !identifier.MatchString(wave.ID) || seenWave[wave.ID] || wave.Trigger != "on_ready" ||
			wave.UnitType != "zerg_zergling" || wave.Count < 1 || wave.Count > 5 ||
			wave.Formation != "compact" || wave.X < 0 || wave.Y < 0 ||
			wave.X >= scenario.ParkSize[0]*32 || wave.Y >= scenario.ParkSize[1]*32 {
			return nil, fmt.Errorf("invalid scenario spawn wave")
		}
		seenWave[wave.ID] = true
	}
	return &scenario, nil
}

// Outcome uses only confirmed park demolition and complete OpenBW actor counts.
func (s *Scenario) Outcome(objectiveDestroyed bool, marines, zerglings int) string {
	if objectiveDestroyed || marines == 0 {
		return "defeat"
	}
	if zerglings == 0 {
		return "victory"
	}
	return ""
}

func (s *Scenario) CheckReady(registry *Registry, proxies map[string]string, ready Ready) error {
	return s.CheckReadyWithRuntime(registry, proxies, ready, 0, 0)
}

func (s *Scenario) CheckReadyWithRuntime(registry *Registry, proxies map[string]string, ready Ready,
	runtimeMarines, runtimeZerglings int) error {
	if registry.Width != s.ParkSize[0] || registry.Height != s.ParkSize[1] {
		return fmt.Errorf("park_size_mismatch: expected %dx%d, got %dx%d", s.ParkSize[0], s.ParkSize[1], registry.Width, registry.Height)
	}
	if ready.Navigation != "native" {
		return fmt.Errorf("native_navigation_unavailable: %s", ready.Navigation)
	}
	validCounts := ready.Marines == len(s.StartingUnits.Marines) &&
		ready.Zerglings == len(s.StartingUnits.Zerglings)
	if ready.Resuming {
		validCounts = runtimeMarines >= 0 && runtimeZerglings >= 0 &&
			ready.Marines >= runtimeMarines && ready.Zerglings >= runtimeZerglings &&
			ready.Marines <= len(s.StartingUnits.Marines)+runtimeMarines &&
			ready.Zerglings <= len(s.StartingUnits.Zerglings)+runtimeZerglings
	}
	if !validCounts {
		return fmt.Errorf("starting_units_missing: marines=%d/%d zerglings=%d/%d", ready.Marines,
			len(s.StartingUnits.Marines), ready.Zerglings, len(s.StartingUnits.Zerglings))
	}
	for _, objective := range s.Objectives {
		if !objective.Required {
			continue
		}
		id, err := s.ObjectiveEntityID(registry, objective.ID)
		if err != nil {
			return err
		}
		if proxies[id] == "" {
			return fmt.Errorf("objective_target_missing: %s", objective.ID)
		}
	}
	return nil
}

func (s *Scenario) ObjectiveEntityID(registry *Registry, objectiveID string) (string, error) {
	for _, objective := range s.Objectives {
		if objective.ID != objectiveID {
			continue
		}
		var match string
		count := 0
		for id, entity := range registry.Entities {
			if entity.Kind == objective.EntityKind && entity.Type == objective.EntityType && !registry.Destroyed[id] {
				match = id
				count++
			}
		}
		if count != 1 {
			return "", fmt.Errorf("objective_ambiguous_or_missing: %s matches=%d", objective.ID, count)
		}
		return match, nil
	}
	return "", fmt.Errorf("objective_not_configured: %s", objectiveID)
}
