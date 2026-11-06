package world

import (
	"path/filepath"
	"testing"
)

func TestConstructionJournalNeverReplaysAmbiguousOrder(t *testing.T) {
	path := filepath.Join(t.TempDir(), "construction.json")
	ledger, err := LoadConstructionLedger(path, "session-a")
	if err != nil {
		t.Fatal(err)
	}
	intent := ConstructionIntent{ID: "build-1", WorkerID: "openbw:2506", BuildingType: "terran_supply_depot", Tile: Point{X: 28, Y: 15}}
	if err := ledger.Reserve(intent, 64, 64); err != nil {
		t.Fatal(err)
	}
	if err := ledger.MarkDispatched(intent.ID); err != nil {
		t.Fatal(err)
	}
	recovered, err := LoadConstructionLedger(path, "session-a")
	if err != nil {
		t.Fatal(err)
	}
	if recovered.MayDispatch(intent.ID) {
		t.Fatal("ambiguous in-flight order replayed after restart")
	}
	if err := recovered.Reserve(intent, 64, 64); err != nil {
		t.Fatalf("idempotent retry failed: %v", err)
	}
	if err := recovered.Bind(ConstructionObservation{IntentID: intent.ID, NativeID: "263", ControllerNativeID: "261", Type: intent.BuildingType, Owner: 1, Tile: intent.Tile, Generation: 1}); err != nil {
		t.Fatal(err)
	}
	if recovered.Intents[intent.ID].ControllerNativeID != "261" {
		t.Fatal("controller identity was not persisted")
	}
	if err := recovered.Bind(ConstructionObservation{IntentID: intent.ID, NativeID: "264", Type: intent.BuildingType, Owner: 1, Tile: intent.Tile, Generation: 1}); err == nil {
		t.Fatal("different native building rebound to one intent")
	}
	if err := recovered.Complete(intent.ID, "263"); err != nil {
		t.Fatal(err)
	}
}

func TestUnconfirmedNativeCreationStaysReservedAndCanBindLater(t *testing.T) {
	path := filepath.Join(t.TempDir(), "construction.json")
	ledger, err := LoadConstructionLedger(path, "session-a")
	if err != nil {
		t.Fatal(err)
	}
	intent := ConstructionIntent{ID: "build-2", WorkerID: "openbw:2506", BuildingType: "terran_academy", Tile: Point{X: 29, Y: 6}}
	if err := ledger.Reserve(intent, 64, 64); err != nil {
		t.Fatal(err)
	}
	if err := ledger.MarkDispatched(intent.ID); err != nil {
		t.Fatal(err)
	}
	if changed, err := ledger.NoteAbsent(intent.ID, 5000, 2400); err != nil || changed {
		t.Fatalf("first absence: changed=%v err=%v", changed, err)
	}
	if changed, err := ledger.NoteAbsent(intent.ID, 7399, 2400); err != nil || changed {
		t.Fatalf("premature unresolved: changed=%v err=%v", changed, err)
	}
	if changed, err := ledger.NoteAbsent(intent.ID, 7400, 2400); err != nil || !changed {
		t.Fatalf("missing unresolved: changed=%v err=%v", changed, err)
	}
	recovered, err := LoadConstructionLedger(path, "session-a")
	if err != nil {
		t.Fatal(err)
	}
	if recovered.MayDispatch(intent.ID) || recovered.Intents[intent.ID].StatusError != "native_creation_unconfirmed" {
		t.Fatalf("unsafe recovery: %+v", recovered.Intents[intent.ID])
	}
	if recovered.Intents[intent.ID].PublishedState() != "unresolved" {
		t.Fatal("restart hid the native creation warning")
	}
	if err := recovered.Bind(ConstructionObservation{IntentID: intent.ID, NativeID: "225", ControllerNativeID: "225", Type: intent.BuildingType, Owner: 1, Tile: intent.Tile, Generation: 1}); err != nil {
		t.Fatal(err)
	}
	if recovered.Intents[intent.ID].StatusError != "" {
		t.Fatal("late native creation did not clear uncertainty")
	}
}

func TestConstructionReservationAndFinitePatchGate(t *testing.T) {
	ledger, err := LoadConstructionLedger(filepath.Join(t.TempDir(), "construction.json"), "session-a")
	if err != nil {
		t.Fatal(err)
	}
	first := ConstructionIntent{ID: "build-1", WorkerID: "openbw:2506", BuildingType: "terran_supply_depot", Tile: Point{X: 28, Y: 15}}
	if err := ledger.Reserve(first, 64, 64); err != nil {
		t.Fatal(err)
	}
	if err := ledger.MarkDispatched(first.ID); err != nil {
		t.Fatal(err)
	}
	second := ConstructionIntent{ID: "build-2", WorkerID: "openbw:2507", BuildingType: "terran_barracks", Tile: Point{X: 30, Y: 16}}
	if err := ledger.Reserve(second, 64, 64); err == nil {
		t.Fatal("overlapping native sites reserved")
	}
	freeDepot := Entity{ID: "openrct2:large_scenery:free#1", Kind: "structure", Type: "terran_supply_depot", Owner: 1,
		Position: Point{X: 28 * 32, Y: 15 * 32}, Geometry: Geometry{
			Cells: []Point{{28, 15}, {29, 15}, {30, 15}, {28, 16}, {29, 16}, {30, 16}},
			Rects: []Rect{{X: 28 * 32, Y: 15 * 32, Width: 96, Height: 64}}}}
	if err := ledger.ValidateFinitePatch(Patch{Additions: []Entity{freeDepot}}); err == nil {
		t.Fatal("free completed scenery accepted")
	}
	wall := Entity{ID: "openrct2:wall:w#1", Kind: "wall", Geometry: Geometry{Rects: []Rect{{X: 29 * 32, Y: 15 * 32, Width: 16, Height: 32}}}}
	if err := ledger.ValidateFinitePatch(Patch{Additions: []Entity{wall}}); err == nil {
		t.Fatal("ordinary edit occupied reserved site")
	}
	path := Entity{ID: "openrct2:path:p#1", Kind: "path", Geometry: Geometry{Cells: []Point{{X: 29, Y: 16}}}}
	if err := ledger.ValidateFinitePatch(Patch{Additions: []Entity{path}}); err == nil {
		t.Fatal("tile geometry occupied reserved site")
	}
	if err := ledger.Bind(ConstructionObservation{IntentID: first.ID, NativeID: "263", Type: first.BuildingType, Owner: 1, Tile: first.Tile, Generation: 1}); err != nil {
		t.Fatal(err)
	}
	if err := ledger.AllowProjection(first.ID, freeDepot.ID); err != nil {
		t.Fatal(err)
	}
	if err := ledger.ValidateFinitePatch(Patch{Additions: []Entity{freeDepot}}); err != nil {
		t.Fatalf("native-bound projection rejected: %v", err)
	}
	wrongOwner := freeDepot
	wrongOwner.Owner = 0
	if err := ledger.ValidateFinitePatch(Patch{Additions: []Entity{wrongOwner}}); err == nil {
		t.Fatal("native projection accepted a forged owner")
	}
	outside := freeDepot
	outside.Geometry.Rects = []Rect{{X: 30 * 32, Y: 15 * 32, Width: 128, Height: 32}}
	if err := ledger.ValidateFinitePatch(Patch{Additions: []Entity{outside}}); err == nil {
		t.Fatal("native projection expanded beyond its reserved footprint")
	}
	ledger.NormalizeNativeProjection(&freeDepot)
	if !freeDepot.NativeOrigin || freeDepot.NativeID != "263" || freeDepot.Collision.Blocks {
		t.Fatalf("native projection would duplicate its collision mask: %+v", freeDepot)
	}
}

func TestRefineryBindingRequiresCurrentGeyserGeneration(t *testing.T) {
	ledger, err := LoadConstructionLedger(filepath.Join(t.TempDir(), "construction.json"), "session-a")
	if err != nil {
		t.Fatal(err)
	}
	intent := ConstructionIntent{ID: "refinery-1", WorkerID: "openbw:2506", BuildingType: "terran_refinery", Tile: Point{X: 34, Y: 8}, GeyserSiteID: "geyser", GeyserGeneration: 2, GeyserNativeID: "10", GeyserControllerID: "10"}
	if err := ledger.Reserve(intent, 64, 64); err != nil {
		t.Fatal(err)
	}
	if err := ledger.MarkDispatched(intent.ID); err != nil {
		t.Fatal(err)
	}
	if err := ledger.CheckGeyser(intent.ID, ResourceState{ResourceObservation: ResourceObservation{SiteID: "geyser", Generation: 3, NativeID: "274", Type: "vespene_geyser", Lifecycle: "deposit"}}); err == nil {
		t.Fatal("stale geyser binding accepted")
	}
	if err := ledger.CheckGeyser(intent.ID, ResourceState{ResourceObservation: ResourceObservation{SiteID: "geyser", Generation: 2, NativeID: "10", Type: "vespene_geyser", Lifecycle: "deposit"}}); err != nil {
		t.Fatal(err)
	}
	if err := ledger.Bind(ConstructionObservation{IntentID: intent.ID, NativeID: "10", ControllerNativeID: "11", Type: "terran_refinery", Owner: 1, Tile: intent.Tile, Generation: 3}); err == nil {
		t.Fatal("refinery rebound to a different native geyser")
	}
	if err := ledger.Bind(ConstructionObservation{IntentID: intent.ID, NativeID: "10", ControllerNativeID: "10", Type: "terran_refinery", Owner: 1, Tile: intent.Tile, Generation: 3}); err != nil {
		t.Fatal(err)
	}
}

func TestConstructionSiteRequiresOwnedClearLevelTerrain(t *testing.T) {
	r := NewRegistry()
	r.Session, r.Revision, r.Width, r.Height = "session-a", 1, 64, 64
	for y := 15; y < 17; y++ {
		for x := 28; x < 31; x++ {
			r.Terrain = append(r.Terrain, Terrain{X: x, Y: y, Height: 24, Walkable: true, ConstructionRights: true})
		}
	}
	intent := ConstructionIntent{ID: "build-1", WorkerID: "openbw:2506", BuildingType: "terran_supply_depot", Tile: Point{X: 28, Y: 15}}
	if err := ValidateConstructionSite(r, intent); err != nil {
		t.Fatal(err)
	}
	r.Terrain[0].ConstructionRights = false
	if err := ValidateConstructionSite(r, intent); err == nil {
		t.Fatal("unowned tile accepted")
	}
	r.Terrain[0].ConstructionRights = true
	r.Terrain[1].Water = 16
	if err := ValidateConstructionSite(r, intent); err == nil {
		t.Fatal("wet tile accepted")
	}
	r.Terrain[1].Water = 0
	r.Terrain[2].Height = 32
	if err := ValidateConstructionSite(r, intent); err == nil {
		t.Fatal("uneven site accepted")
	}
}
