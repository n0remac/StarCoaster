package world

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func validV2(t *testing.T) Scenario {
	t.Helper()
	s, err := LoadScenario(filepath.Join("..", "..", "scenarios", "frontier-outpost.json"))
	if err != nil {
		t.Fatal(err)
	}
	s.Version = 2
	s.SpawnWaves = nil
	s.Objectives[0].Description = "Defend Frontier Carousel"
	s.Objectives[0].EntityName = "Frontier Carousel"
	s.Victory.AllWavesCleared = true
	s.SpawnZones = map[string]SpawnZone{"east": {Tiles: [][2]int{{43, 56}, {44, 56}, {45, 56}}}}
	zero := 0
	s.Waves = []ScenarioWave{
		{ID: "first", Trigger: WaveTrigger{Type: "on_ready"}, Groups: []WaveGroup{{UnitType: "zerg_zergling", Count: 1, SpawnZone: "east"}}},
		{ID: "timed", Trigger: WaveTrigger{Type: "elapsed_frames", Frames: &zero}, Groups: []WaveGroup{{UnitType: "zerg_zergling", Count: 1, SpawnZone: "east"}}},
		{ID: "dependent", Trigger: WaveTrigger{Type: "wave_cleared", WaveID: "timed"}, Groups: []WaveGroup{{UnitType: "zerg_zergling", Count: 1, SpawnZone: "east"}}},
	}
	return *s
}

func loadV2ForTest(t *testing.T, s Scenario) error {
	t.Helper()
	data, err := json.Marshal(s)
	if err != nil {
		t.Fatal(err)
	}
	path := filepath.Join(t.TempDir(), "scenario.json")
	if err := os.WriteFile(path, data, 0600); err != nil {
		t.Fatal(err)
	}
	_, err = LoadScenario(path)
	return err
}

func TestV2ScenarioValidation(t *testing.T) {
	base := validV2(t)
	if err := loadV2ForTest(t, base); err != nil {
		t.Fatal(err)
	}
	tests := []struct {
		name   string
		mutate func(*Scenario)
	}{
		{"duplicate objective", func(s *Scenario) { s.Objectives = append(s.Objectives, s.Objectives[0]) }},
		{"empty name", func(s *Scenario) { s.Objectives[0].EntityName = "  " }},
		{"duplicate zone tile", func(s *Scenario) { s.SpawnZones["east"] = SpawnZone{Tiles: [][2]int{{43, 56}, {43, 56}}} }},
		{"outside zone", func(s *Scenario) { s.SpawnZones["east"] = SpawnZone{Tiles: [][2]int{{64, 56}}} }},
		{"scheduled marines", func(s *Scenario) { s.Waves[0].Groups[0].UnitType = "terran_marine" }},
		{"zero count", func(s *Scenario) { s.Waves[0].Groups[0].Count = 0 }},
		{"unknown zone", func(s *Scenario) { s.Waves[0].Groups[0].SpawnZone = "missing" }},
		{"unknown wave", func(s *Scenario) { s.Waves[2].Trigger.WaveID = "missing" }},
		{"cycle", func(s *Scenario) { s.Waves[1].Trigger = WaveTrigger{Type: "wave_cleared", WaveID: "dependent"} }},
		{"invalid trigger field", func(s *Scenario) { s.Waves[0].Trigger.WaveID = "timed" }},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			s := validV2(t)
			tc.mutate(&s)
			if err := loadV2ForTest(t, s); err == nil {
				t.Fatal("invalid v2 scenario accepted")
			}
		})
	}
}

func TestV2RejectsUnknownFields(t *testing.T) {
	s := validV2(t)
	data, _ := json.Marshal(s)
	data = []byte(strings.Replace(string(data), `"type":"on_ready"`, `"type":"on_ready","surprise":true`, 1))
	path := filepath.Join(t.TempDir(), "scenario.json")
	if err := os.WriteFile(path, data, 0600); err != nil {
		t.Fatal(err)
	}
	if _, err := LoadScenario(path); err == nil || !strings.Contains(err.Error(), "unknown field") {
		t.Fatalf("unknown trigger field: %v", err)
	}
}
