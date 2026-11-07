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
	base := world.Entity{ID: "scenario:base", Kind: "structure", Type: "terran_command_center",
		Owner: 1, Position: world.Point{X: 20 * 32, Y: 8 * 32},
		Geometry: world.Geometry{Rects: []world.Rect{{X: 20 * 32, Y: 8 * 32, Width: 4 * 32, Height: 3 * 32}}}}
	if err := s.validateFiniteSnapshot([]world.Entity{base}); err != nil {
		t.Fatalf("valid authored native base rejected: %v", err)
	}
	spoofed := base
	spoofed.Owner = 2
	if err := s.validateFiniteSnapshot([]world.Entity{spoofed}); err == nil {
		t.Fatal("authored native base owner spoof accepted")
	}
	spoofed = base
	spoofed.Geometry.Rects = []world.Rect{{X: 0, Y: 0, Width: 32, Height: 32}}
	if err := s.validateFiniteSnapshot([]world.Entity{spoofed}); err == nil {
		t.Fatal("authored native base footprint spoof accepted")
	}
	if err := ledger.MarkAuthoredDestroyed("scenario:base"); err != nil {
		t.Fatal(err)
	}
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

func TestInitialNativeCommandCenterDoesNotDuplicateParkCollision(t *testing.T) {
	scenario, err := world.LoadScenario(filepath.Join("..", "..", "scenarios", "economy-e1", "scenario.json"))
	if err != nil {
		t.Fatal(err)
	}
	s := &service{scenario: scenario}
	base := world.Entity{ID: "scenario:base", Source: "openrct2", Kind: "structure",
		Type: "terran_command_center", Owner: 1,
		Position:  world.Point{X: 20 * 32, Y: 8 * 32},
		Geometry:  world.Geometry{Rects: []world.Rect{{X: 20 * 32, Y: 8 * 32, Width: 128, Height: 96}}},
		Collision: world.Collision{Blocks: true}}
	s.normalizeAuthoredNativeProjection(&base)
	if base.NativeOrigin || base.Collision.Blocks {
		t.Fatalf("initial native base retained a duplicate park obstacle: %+v", base)
	}
	registry := world.NewRegistry()
	registry.Width, registry.Height = 64, 64
	registry.Entities[base.ID] = base
	transform, err := world.Fit(64, 64, 256, 256)
	if err != nil {
		t.Fatal(err)
	}
	mask, err := world.DeriveNavigation(registry, transform, 256, 256)
	if err != nil {
		t.Fatal(err)
	}
	if mask.BlockedPixel(transform.X(20*32+16), transform.Y(8*32+16)) {
		t.Fatal("native base remains blocked in the park navigation mask")
	}
	ordinary := base
	ordinary.ID = "openrct2:large_scenery:forged#1"
	ordinary.NativeOrigin = false
	ordinary.Collision.Blocks = true
	s.normalizeAuthoredNativeProjection(&ordinary)
	if ordinary.NativeOrigin || !ordinary.Collision.Blocks {
		t.Fatalf("ordinary scenery lost its collision: %+v", ordinary)
	}
	registry.Entities[ordinary.ID] = ordinary
	delete(registry.Entities, base.ID)
	mask, err = world.DeriveNavigation(registry, transform, 256, 256)
	if err != nil {
		t.Fatal(err)
	}
	if !mask.BlockedPixel(transform.X(20*32+16), transform.Y(8*32+16)) {
		t.Fatal("ordinary scenery did not retain its park collision")
	}
}
