package world

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
)

func parkDefenseScenario(t *testing.T) *Scenario {
	t.Helper()
	s := &Scenario{Version: 2, ID: "park", Mode: "park_defense", DisplayName: "Park", ParkFile: "run-data/park/save/park.park", ParkSize: [2]int{64, 64}}
	s.StartingUnits.Marines = [][2]int{{20, 20}, {21, 20}}
	s.InitialAI.Strategy = "park_defense"
	s.SpawnZones = map[string]SpawnZone{
		"north": {Tiles: [][2]int{{30, 10}, {31, 10}}},
		"south": {Tiles: [][2]int{{30, 50}, {31, 50}}},
	}
	s.ParkDefense = &ParkDefenseWaves{InitialDelayFrames: 2880, IntervalFrames: 2880,
		UnitsPerWave: 8, ManualCooldownFrames: 360, SpawnZones: []string{"north", "south"}}
	return s
}

func TestParkDefenseValidationAndOutcome(t *testing.T) {
	s := parkDefenseScenario(t)
	path := filepath.Join(t.TempDir(), "park.json")
	write := func() error {
		data, err := json.Marshal(s)
		if err != nil {
			return err
		}
		return os.WriteFile(path, data, 0600)
	}
	if err := write(); err != nil {
		t.Fatal(err)
	}
	loaded, err := LoadScenario(path)
	if err != nil {
		t.Fatal(err)
	}
	if loaded.Outcome(true, 0, 0) != "" {
		t.Fatal("park management outcome was replaced")
	}
	s.ParkDefense.SpawnZones[1] = "missing"
	if err := write(); err != nil {
		t.Fatal(err)
	}
	if _, err := LoadScenario(path); err == nil {
		t.Fatal("unknown zone accepted")
	}
}

func TestParkDefenseRecurringFramesManualAndRecovery(t *testing.T) {
	s := parkDefenseScenario(t)
	r := NewScenarioRuntime(s, "session")
	if err := r.AcceptFrame(100, 1, false); err == nil {
		t.Fatal("incomplete frame accepted")
	}
	if err := r.AcceptFrame(100, 1, true); err != nil {
		t.Fatal(err)
	}
	if !r.Trigger(s) || r.NextAutomaticFrame != 2980 {
		t.Fatalf("deadline: %d", r.NextAutomaticFrame)
	}
	if err := r.AcceptFrame(2979, 2, true); err != nil {
		t.Fatal(err)
	}
	if r.Trigger(s) {
		t.Fatal("early wave")
	}
	if err := r.AcceptFrame(2980, 3, true); err != nil {
		t.Fatal(err)
	}
	if !r.Trigger(s) || r.Waves[0].ID != "periodic-0001" {
		t.Fatalf("first wave: %+v", r.Waves)
	}
	deadline := r.NextAutomaticFrame
	id, err := r.RequestManual(s, "request-1", 1, 1)
	if err != nil || id != "manual-0002" || r.NextAutomaticFrame != deadline {
		t.Fatalf("manual: %s %v", id, err)
	}
	if replay, err := r.RequestManual(s, "request-1", 1, 1); err != nil || replay != id || len(r.Waves) != 2 {
		t.Fatalf("idempotent replay: %s %v", replay, err)
	}
	if _, err := r.RequestManual(s, "request-2", 1, 2); err == nil {
		t.Fatal("cooldown ignored")
	}
	zone, ok := r.WaveZone(s, 1, 0)
	if !ok || zone.Tiles[0] != [2]int{30, 50} {
		t.Fatalf("manual zone: %+v", zone)
	}
	data, err := json.Marshal(r)
	if err != nil {
		t.Fatal(err)
	}
	var restored ScenarioRuntime
	if err := json.Unmarshal(data, &restored); err != nil {
		t.Fatal(err)
	}
	if err := restored.Validate(s, "session"); err != nil {
		t.Fatal(err)
	}
	for i := range restored.Waves {
		restored.Waves[i].State = "active"
	}
	if err := restored.AcceptFrame(deadline, 4, true); err != nil {
		t.Fatal(err)
	}
	if !restored.Trigger(s) || len(restored.Waves) != 3 || restored.Waves[2].ID != "periodic-0003" {
		t.Fatalf("second automatic wave: %+v", restored.Waves)
	}
	if err := restored.AcceptFrame(deadline+10000, 5, true); err != nil {
		t.Fatal(err)
	}
	if restored.Trigger(s) {
		t.Fatal("unsettled wave created unlimited backlog")
	}
	if restored.NextAutomaticFrame != deadline+2880 {
		t.Fatal("blocked wave changed deadline")
	}
	for i := range restored.Waves {
		restored.Waves[i].State = "active"
	}
	if !restored.Trigger(s) || len(restored.Waves) != 4 || restored.NextAutomaticFrame != restored.LastFrame+2880 {
		t.Fatal("outage catch-up did not create exactly one wave")
	}
}

func TestParkDefenseHistoryRemainsBounded(t *testing.T) {
	s := parkDefenseScenario(t)
	r := NewScenarioRuntime(s, "session")
	for i := 0; i < 70; i++ {
		r.LastFrame = i + 1
		r.newParkDefenseWave(s, "periodic")
		r.Waves[i].State = "cleared"
	}
	r.Waves[69].State = "active"
	pruned := r.PruneParkDefenseHistory(s)
	if len(r.Waves) != 65 || r.Waves[0].ID != "periodic-0006" ||
		r.Waves[len(r.Waves)-1].ID != "periodic-0070" || len(pruned) != 0 {
		t.Fatalf("completed history not bounded: count=%d first=%s", len(r.Waves), r.Waves[0].ID)
	}
	if r.TotalTriggered != 70 || r.NextWaveSequence != 71 {
		t.Fatal("pruning reset durable sequence")
	}
}

func TestBlockedManualPlacementDoesNotStopScheduledWave(t *testing.T) {
	s := parkDefenseScenario(t)
	r := NewScenarioRuntime(s, "session")
	if err := r.AcceptFrame(100, 1, true); err != nil {
		t.Fatal(err)
	}
	r.Trigger(s)
	if _, err := r.RequestManual(s, "manual-1", 1, 1); err != nil {
		t.Fatal(err)
	}
	r.Waves[0].State = "spawning"
	if err := r.AcceptFrame(2980, 2, true); err != nil {
		t.Fatal(err)
	}
	if !r.Trigger(s) || len(r.Waves) != 2 || r.Waves[1].ID != "periodic-0002" {
		t.Fatalf("manual placement blocked automatic deadline: %+v", r.Waves)
	}
	if wi, ui, ok := r.NextPlannedExcept(map[[2]int]bool{{0, 0}: true}); !ok || wi != 0 || ui != 1 {
		t.Fatalf("did not skip deferred placement: %d %d %v", wi, ui, ok)
	}
	blocked := map[[2]int]bool{}
	for index := range r.Waves[0].Units {
		blocked[[2]int{0, index}] = true
	}
	if wi, _, ok := r.NextPlannedExcept(blocked); !ok || wi != 1 {
		t.Fatalf("automatic wave could not dispatch around blocked manual zone: %d %v", wi, ok)
	}
}

func TestParkDefenseTierSelectionUsesDurableSequence(t *testing.T) {
	s := parkDefenseScenario(t)
	s.ParkDefense.UnitsPerWave = 0
	s.ParkDefense.WaveTiers = []WaveTier{
		{FromWave: 1, Groups: []WaveTierGroup{{UnitType: "zerg_zergling", Count: 2}}},
		{FromWave: 3, Groups: []WaveTierGroup{{UnitType: "zerg_hydralisk", Count: 1}, {UnitType: "zerg_ultralisk", Count: 1}}},
	}
	r := NewScenarioRuntime(s, "session")
	if err := r.AcceptFrame(100, 1, true); err != nil {
		t.Fatal(err)
	}
	r.Trigger(s)
	if err := r.AcceptFrame(2980, 2, true); err != nil {
		t.Fatal(err)
	}
	r.Trigger(s)
	deadline := r.NextAutomaticFrame
	if _, err := r.RequestManual(s, "manual-1", 1, 1); err != nil {
		t.Fatal(err)
	}
	if r.NextAutomaticFrame != deadline {
		t.Fatal("manual wave changed timer")
	}
	if err := r.AcceptFrame(deadline, 3, true); err != nil {
		t.Fatal(err)
	}
	r.Waves[0].State = "active"
	r.Trigger(s)
	if len(r.Waves) != 3 || r.Waves[2].Sequence != 3 || len(r.Waves[2].Composition) != 2 {
		t.Fatalf("wrong durable tier: %+v", r.Waves)
	}
	if r.Waves[2].Units[0].UnitType != "zerg_hydralisk" || r.Waves[2].Units[1].UnitType != "zerg_ultralisk" {
		t.Fatalf("wrong mixed composition: %+v", r.Waves[2].Units)
	}
	if err := r.Validate(s, "session"); err != nil {
		t.Fatal(err)
	}
}

func TestParkDefenseTierValidation(t *testing.T) {
	base := parkDefenseScenario(t)
	base.ParkDefense.UnitsPerWave = 0
	base.ParkDefense.WaveTiers = []WaveTier{
		{FromWave: 1, Groups: []WaveTierGroup{{UnitType: "zerg_zergling", Count: 8}}},
		{FromWave: 3, Groups: []WaveTierGroup{{UnitType: "zerg_hydralisk", Count: 2}}},
	}
	load := func(s *Scenario) error {
		data, err := json.Marshal(s)
		if err != nil {
			t.Fatal(err)
		}
		path := filepath.Join(t.TempDir(), "park.json")
		if err := os.WriteFile(path, data, 0600); err != nil {
			t.Fatal(err)
		}
		_, err = LoadScenario(path)
		return err
	}
	if err := load(base); err != nil {
		t.Fatal(err)
	}
	for name, change := range map[string]func(*Scenario){
		"legacy count mixed":  func(s *Scenario) { s.ParkDefense.UnitsPerWave = 8 },
		"first tier late":     func(s *Scenario) { s.ParkDefense.WaveTiers[0].FromWave = 2 },
		"duplicate threshold": func(s *Scenario) { s.ParkDefense.WaveTiers[1].FromWave = 1 },
		"oversized":           func(s *Scenario) { s.ParkDefense.WaveTiers[1].Groups[0].Count = 65 },
		"player unit":         func(s *Scenario) { s.ParkDefense.WaveTiers[1].Groups[0].UnitType = "terran_marine" },
	} {
		s := parkDefenseScenario(t)
		s.ParkDefense.UnitsPerWave = 0
		s.ParkDefense.WaveTiers = []WaveTier{
			{FromWave: 1, Groups: []WaveTierGroup{{UnitType: "zerg_zergling", Count: 8}}},
			{FromWave: 3, Groups: []WaveTierGroup{{UnitType: "zerg_hydralisk", Count: 2}}},
		}
		change(s)
		if err := load(s); err == nil {
			t.Fatalf("accepted %s", name)
		}
	}
}
