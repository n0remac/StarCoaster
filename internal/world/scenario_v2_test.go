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
	s, err := LoadScenario(filepath.Join("..", "..", "scenarios", "frontier-outpost", "scenario.json"))
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
	base.ProductionFixture.TerranGas = 250
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
		{"negative starting gas", func(s *Scenario) { s.ProductionFixture.TerranGas = -1 }},
		{"excess starting gas", func(s *Scenario) { s.ProductionFixture.TerranGas = 100001 }},
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

func TestV2MixedEnemyWaveValidation(t *testing.T) {
	s := validV2(t)
	s.Waves[0].Groups = []WaveGroup{
		{UnitType: "zerg_zergling", Count: 2, SpawnZone: "east"},
		{UnitType: "zerg_hydralisk", Count: 1, SpawnZone: "east"},
		{UnitType: "zerg_ultralisk", Count: 1, SpawnZone: "east"},
	}
	if err := loadV2ForTest(t, s); err != nil {
		t.Fatal(err)
	}
	for _, kind := range []string{"terran_marine", "terran_firebat", "missing"} {
		s.Waves[0].Groups[1].UnitType = kind
		if err := loadV2ForTest(t, s); err == nil {
			t.Fatalf("accepted unsupported wave unit %s", kind)
		}
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

func TestV2NamedObjectiveSelectsUniqueRide(t *testing.T) {
	s := validV2(t)
	r := NewRegistry()
	first := exampleEntity("openrct2:ride:100#1")
	first.Kind, first.Type, first.Name = "ride", "rct2.ride.mgr1", "Frontier Carousel"
	second := exampleEntity("openrct2:ride:101#1")
	second.Kind, second.Type, second.Name = "ride", "rct2.ride.mgr1", "Other Carousel"
	if err := r.Replace("session-a", 1, 64, 64, []Entity{first, second}, nil); err != nil {
		t.Fatal(err)
	}
	if id, err := s.ObjectiveEntityID(r, "defend-carousel"); err != nil || id != first.ID {
		t.Fatalf("named selector: %s %v", id, err)
	}
	s.Objectives[0].EntityName = ""
	if _, err := s.ObjectiveEntityID(r, "defend-carousel"); err == nil {
		t.Fatal("type-only ambiguous selector accepted")
	}
	s.Objectives[0].EntityName = "Other Carousel"
	if id, err := s.ObjectiveEntityID(r, "defend-carousel"); err != nil || id != second.ID {
		t.Fatalf("second named selector: %s %v", id, err)
	}
}
