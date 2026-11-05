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
