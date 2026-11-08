package main

import (
	"path/filepath"
	"testing"

	"starcoaster/internal/world"
)

func TestGeneratedEnemyBaseProjectionAndDestroyedSnapshot(t *testing.T) {
	scenario, err := world.LoadScenario(filepath.Join("..", "..", "scenarios", "economy-e1", "scenario.json"))
	if err != nil {
		t.Fatal(err)
	}
	structure := world.ScenarioStructure{ID: "enemy-hatchery", Type: "zerg_hatchery",
		Faction: "zerg", Tile: [2]int{8, 31}}
	scenario.EnemyBase = &world.ScenarioEnemyBase{Structures: []world.ScenarioStructure{structure}}
	scenario.InitialStructures = append(scenario.InitialStructures, structure)
	ledger, err := world.LoadConstructionLedger(filepath.Join(t.TempDir(), "construction.json"), "session")
	if err != nil {
		t.Fatal(err)
	}
	s := &service{scenario: scenario, construction: ledger, registry: world.NewRegistry()}
	base := world.Entity{ID: "scenario:enemy-hatchery", Kind: "structure", Type: "zerg_hatchery",
		Owner: 0, Position: world.Point{X: 8 * 32, Y: 31 * 32},
		Geometry: world.Geometry{Rects: []world.Rect{{X: 8 * 32, Y: 31 * 32,
			Width: 4 * 32, Height: 3 * 32}}}, Collision: world.Collision{Blocks: true}}
	s.normalizeAuthoredNativeProjection(&base)
	if base.Collision.Blocks {
		t.Fatal("native colony has duplicate park obstacle")
	}
	if err := s.validateFiniteSnapshot([]world.Entity{base}); err != nil {
		t.Fatal(err)
	}
	if err := s.validateFinitePatch(world.Patch{Removals: []string{base.ID}}); err == nil {
		t.Fatal("manual native colony removal accepted")
	}
	spoofed := base
	spoofed.Owner = 1
	if err := s.validateFiniteSnapshot([]world.Entity{spoofed}); err == nil {
		t.Fatal("wrong native colony owner accepted")
	}
	if err := ledger.MarkAuthoredDestroyed(base.ID); err != nil {
		t.Fatal(err)
	}
	if err := s.validateFiniteSnapshot([]world.Entity{base}); err == nil {
		t.Fatal("destroyed colony restored from snapshot")
	}
}
