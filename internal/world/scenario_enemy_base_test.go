package world

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
)

func generatedEnemyScenario(t *testing.T, blocked bool) map[string]any {
	t.Helper()
	data, err := os.ReadFile(filepath.Join("..", "..", "scenarios", "economy-e1", "scenario.json"))
	if err != nil {
		t.Fatal(err)
	}
	var v map[string]any
	if err := json.Unmarshal(data, &v); err != nil {
		t.Fatal(err)
	}
	e := v["economy"].(map[string]any)
	e["layout_policy"], e["policy_version"], e["layout_seed"] = "generated", 2, "0123456789abcdef"
	e["layout_state"] = "ready"
	v["spawn_zones"] = map[string]any{}
	p := v["park_defense"].(map[string]any)
	p["spawn_policy"], p["spawn_zones"] = "base_production", []any{}
	p["wave_tiers"] = []any{map[string]any{"from_wave": 1,
		"groups": []any{map[string]any{"unit_type": "zerg_zergling", "count": 8}}}}
	base := map[string]any{"version": 1, "layout_policy": "generated", "policy_version": 1,
		"layout_seed": "0123456789abcdef", "layout_state": "ready",
		"structures": []any{
			map[string]any{"id": "enemy-hatchery", "type": "zerg_hatchery", "faction": "zerg", "tile": []int{8, 31}},
			map[string]any{"id": "enemy-spawning-pool", "type": "zerg_spawning_pool", "faction": "zerg", "tile": []int{13, 32}}},
		"supply_tile": []int{16, 34}, "assembly_tile": []int{12, 35}, "approach_tile": []int{12, 38},
		"terran_approach_tile": []int{24, 18}}
	if blocked {
		base["layout_state"], base["blocked_reason"] = "blocked", "no_valid_perimeter_site"
		base["structures"], base["supply_tile"] = []any{}, []int{}
		base["assembly_tile"], base["approach_tile"], base["terran_approach_tile"] = []int{}, []int{}, []int{}
	} else {
		v["initial_structures"] = append(v["initial_structures"].([]any), base["structures"].([]any)...)
	}
	v["enemy_base"] = base
	return v
}

func loadEnemyScenario(t *testing.T, v map[string]any) (*Scenario, error) {
	t.Helper()
	data, err := json.Marshal(v)
	if err != nil {
		t.Fatal(err)
	}
	path := filepath.Join(t.TempDir(), "scenario.json")
	if err := os.WriteFile(path, data, 0600); err != nil {
		t.Fatal(err)
	}
	return LoadScenario(path)
}

func TestGeneratedEnemyBaseBootstrapAndNoFreeWaves(t *testing.T) {
	for _, blocked := range []bool{false, true} {
		s, err := loadEnemyScenario(t, generatedEnemyScenario(t, blocked))
		if err != nil {
			t.Fatal(err)
		}
		r := NewScenarioRuntime(s, "one-session")
		if err := r.AcceptFrame(100, 1, true); err != nil {
			t.Fatal(err)
		}
		r.MarkEconomyReady(100)
		for frame := 200; frame <= 10000; frame += 100 {
			if err := r.AcceptFrame(frame, uint64(frame), true); err != nil {
				t.Fatal(err)
			}
			if r.Trigger(s) {
				t.Fatal("base policy created free wave")
			}
		}
		if len(r.Waves) != 0 {
			t.Fatalf("free waves: %+v", r.Waves)
		}
		if _, err := r.RequestManual(s, "free", 1, 1); err == nil {
			t.Fatal("manual free wave accepted")
		}
		if err := r.Validate(s, "one-session"); err != nil {
			t.Fatal(err)
		}
		copy := *r
		copy.Waves = []RuntimeWave{{ID: "legacy", TemplateID: "park-defense", State: "triggered"}}
		if err := copy.Validate(s, "one-session"); err == nil {
			t.Fatal("legacy free wave accepted")
		}
	}
}

func TestGeneratedEnemyBaseRejectsMissingProjectionAndOverlap(t *testing.T) {
	v := generatedEnemyScenario(t, false)
	v["initial_structures"] = v["initial_structures"].([]any)[:1]
	if _, err := loadEnemyScenario(t, v); err == nil {
		t.Fatal("missing projections accepted")
	}
	v = generatedEnemyScenario(t, false)
	structures := v["enemy_base"].(map[string]any)["structures"].([]any)
	structures[0].(map[string]any)["tile"] = []int{20, 8}
	v["initial_structures"].([]any)[1].(map[string]any)["tile"] = []int{20, 8}
	if _, err := loadEnemyScenario(t, v); err == nil {
		t.Fatal("economy overlap accepted")
	}
}

func TestProducedZerglingsPermitBridgeReadinessRecovery(t *testing.T) {
	v := generatedEnemyScenario(t, false)
	base := v["enemy_base"].(map[string]any)
	base["version"], base["initial_minerals"], base["minimum_supply"], base["max_train_orders"] = 2, 300, 16, 6
	s, err := loadEnemyScenario(t, v)
	if err != nil {
		t.Fatal(err)
	}
	r := NewRegistry()
	r.Width, r.Height = s.ParkSize[0], s.ParkSize[1]
	ready := Ready{Navigation: "native", Zerglings: 2}
	if err := s.CheckReadyWithRuntimeState(r, nil, ready, 0, 2, false); err != nil {
		t.Fatalf("reconciled native pair blocked bridge restart: %v", err)
	}
	ready.Zerglings = 3
	if err := s.CheckReadyWithRuntimeState(r, nil, ready, 0, 2, false); err == nil {
		t.Fatal("unregistered native Zergling accepted")
	}
	ready.Zerglings = 2
	ready.StaticMorphedZerglingIDs = []string{"openbw:2511"}
	if err := s.CheckReadyWithRuntimeState(r, nil, ready, 0, 1, false); err != nil {
		t.Fatalf("native static larva morph blocked bridge restart: %v", err)
	}
	for _, ids := range [][]string{{"openbw:3001"}, {"openbw:2511", "openbw:2511"}, {"openbw:2499"}} {
		ready.StaticMorphedZerglingIDs = ids
		if err := s.CheckReadyWithRuntimeState(r, nil, ready, 0, 1, false); err == nil {
			t.Fatalf("invalid static morph identities accepted: %v", ids)
		}
	}
}

func TestGeneratedEnemyBaseRejectsInvalidProductionBudget(t *testing.T) {
	v := generatedEnemyScenario(t, false)
	base := v["enemy_base"].(map[string]any)
	base["version"], base["initial_minerals"], base["minimum_supply"], base["max_train_orders"] = 2, 300, 16, 6
	if _, err := loadEnemyScenario(t, v); err != nil {
		t.Fatal(err)
	}
	base["initial_minerals"] = 100000
	if _, err := loadEnemyScenario(t, v); err == nil {
		t.Fatal("unbounded enemy bank accepted")
	}
	base["initial_minerals"] = 300
	base["max_train_orders"] = 7
	if _, err := loadEnemyScenario(t, v); err == nil {
		t.Fatal("more orders than finite bank accepted")
	}
}
