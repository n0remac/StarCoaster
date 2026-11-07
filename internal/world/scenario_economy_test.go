package world

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestFiniteEconomyFixtureAndLegacyIsolation(t *testing.T) {
	path := filepath.Join("..", "..", "scenarios", "economy-e1", "scenario.json")
	s, err := LoadScenario(path)
	if err != nil {
		t.Fatal(err)
	}
	if s.Economy == nil || s.Economy.Mode != "finite" || len(s.Economy.StartingEntities) != 12 {
		t.Fatalf("finite bootstrap missing: %+v", s.Economy)
	}
	if s.UnlimitedResources || s.ProductionFixture.TerranMinerals != 0 {
		t.Fatal("finite bootstrap still uses legacy grants")
	}
	legacy, err := LoadScenario(filepath.Join("..", "..", "scenarios", "frontier-outpost", "scenario.json"))
	if err != nil || legacy.Economy != nil {
		t.Fatalf("legacy scenario changed: %v %+v", err, legacy.Economy)
	}
	for _, tc := range []struct {
		name string
		edit func(map[string]any)
		want string
	}{
		{"unlimited", func(v map[string]any) { v["unlimited_resources"] = true }, "finite economy"},
		{"hidden supply", func(v map[string]any) {
			v["production_fixture"] = map[string]any{"terran_minerals": 50, "native_supply_depot": []int{4, 4}}
		}, "finite economy"},
		{"duplicate site", func(v map[string]any) {
			e := v["economy"].(map[string]any)["starting_entities"].([]any)
			e[1].(map[string]any)["tile"] = e[2].(map[string]any)["tile"]
		}, "economy"},
		{"missing visible base", func(v map[string]any) { v["initial_structures"] = []any{} }, "economy base projection"},
	} {
		t.Run(tc.name, func(t *testing.T) {
			data, _ := os.ReadFile(path)
			var v map[string]any
			_ = json.Unmarshal(data, &v)
			tc.edit(v)
			data, _ = json.Marshal(v)
			candidate := filepath.Join(t.TempDir(), "scenario.json")
			_ = os.WriteFile(candidate, data, 0600)
			if _, err := LoadScenario(candidate); err == nil || !strings.Contains(err.Error(), tc.want) {
				t.Fatalf("accepted invalid economy: %v", err)
			}
		})
	}
}

func TestGeneratedEconomyPolicyAndBlockedBootstrap(t *testing.T) {
	path := filepath.Join("..", "..", "scenarios", "economy-e1", "scenario.json")
	data, err := os.ReadFile(path)
	if err != nil { t.Fatal(err) }
	for _, blocked := range []bool{false, true} {
		var scenario map[string]any
		if err := json.Unmarshal(data, &scenario); err != nil { t.Fatal(err) }
		economy := scenario["economy"].(map[string]any)
		economy["layout_policy"] = "generated"
		economy["policy_version"] = 1
		economy["layout_seed"] = "0123456789abcdef"
		if blocked {
			economy["layout_state"] = "blocked"
			economy["blocked_reason"] = "no_native_valid_economy_site"
			economy["starting_entities"] = []any{}
			economy["initial_balances"] = map[string]any{"minerals": 0, "gas": 0}
			scenario["initial_structures"] = []any{}
		} else { economy["layout_state"] = "ready" }
		encoded, _ := json.Marshal(scenario)
		candidate := filepath.Join(t.TempDir(), "scenario.json")
		if err := os.WriteFile(candidate, encoded, 0600); err != nil { t.Fatal(err) }
		loaded, err := LoadScenario(candidate)
		if err != nil { t.Fatalf("generated blocked=%v: %v", blocked, err) }
		if loaded.Economy.LayoutState != economy["layout_state"] {
			t.Fatalf("lost generated layout state: %+v", loaded.Economy)
		}
	}
}

func TestFiniteEconomyWaveClockStartsOnlyAfterBootstrap(t *testing.T) {
	for _, state := range []string{"ready", "blocked"} {
		s := &Scenario{Version: 2, ID: "ordinary", Mode: "park_defense",
			Economy: &ScenarioEconomy{Mode: "finite", LayoutState: state},
			ParkDefense: &ParkDefenseWaves{InitialDelayFrames: 2880,
				IntervalFrames: 2880, SpawnPolicy: "automatic_perimeter"}}
		r := NewScenarioRuntime(s, "session")
		if err := r.AcceptFrame(100, 1, true); err != nil { t.Fatal(err) }
		if r.Trigger(s) || r.NextAutomaticFrame != 0 {
			t.Fatalf("wave clock advanced before bootstrap state=%s: %+v", state, r)
		}
		if err := r.AcceptFrame(200, 2, true); err != nil { t.Fatal(err) }
		r.MarkEconomyReady(200)
		if state == "blocked" {
			if r.Trigger(s) || r.NextAutomaticFrame != 0 {
				t.Fatalf("blocked layout started waves: %+v", r)
			}
		} else if !r.Trigger(s) || r.NextAutomaticFrame != 3080 {
			t.Fatalf("ready layout missed fresh wave clock: %+v", r)
		}
	}
}
