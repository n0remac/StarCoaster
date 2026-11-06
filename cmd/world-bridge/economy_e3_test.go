package main

import (
	"path/filepath"
	"testing"

	"starcoaster/internal/world"
)

func TestAuthoredWorkerDefersExactIdentityToNativeController(t *testing.T) {
	s := &service{actors: world.NewActorRegistry("session-a")}
	if !s.constructionWorker("openbw:2506") {
		t.Fatal("authored SCV was blocked before native identity validation")
	}
	if s.constructionWorker("scenario:worker-a") {
		t.Fatal("non-native worker ID accepted")
	}
}

func TestFiniteBridgeRejectsUnboundStructureAndDirectSpawn(t *testing.T) {
	scenario, err := world.LoadScenario(filepath.Join("..", "..", "scenarios", "economy-e1", "scenario.json"))
	if err != nil {
		t.Fatal(err)
	}
	ledger, err := world.LoadConstructionLedger(filepath.Join(t.TempDir(), "construction.json"), "session-a")
	if err != nil {
		t.Fatal(err)
	}
	s := &service{scenario: scenario, construction: ledger, registry: world.NewRegistry()}
	free := world.Entity{ID: "openrct2:large_scenery:free#1", Kind: "structure", Type: "terran_barracks", Owner: 1}
	if err := s.validateFinitePatch(world.Patch{Additions: []world.Entity{free}}); err == nil {
		t.Fatal("unbound player Barracks accepted by bridge")
	}
	if err := s.validateFinitePatch(world.Patch{Removals: []string{"scenario:base"}}); err == nil {
		t.Fatal("authored native base could be removed and rebuilt for free")
	}
	if err := s.validateFinitePatch(world.Patch{Terrain: []world.Terrain{{X: 20, Y: 8}}}); err == nil {
		t.Fatal("ordinary park edit entered the native base footprint")
	}
	if err := ledger.MarkAuthoredDestroyed("scenario:base"); err != nil {
		t.Fatal(err)
	}
	base := world.Entity{ID: "scenario:base", Kind: "structure", Type: "terran_command_center",
		Owner: 1, Position: world.Point{X: 20 * 32, Y: 8 * 32}}
	if err := s.validateFiniteSnapshot([]world.Entity{base}); err == nil {
		t.Fatal("destroyed native base was restored through a snapshot")
	}
	if !s.rejectDirectEconomySpawn() {
		t.Fatal("finite economy still allows direct free spawn")
	}
	s.scenario = nil
	if s.rejectDirectEconomySpawn() {
		t.Fatal("legacy scenario lost direct spawn behavior")
	}
}
