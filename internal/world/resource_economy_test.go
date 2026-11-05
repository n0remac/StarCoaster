package world

import (
	"encoding/json"
	"os"
	"testing"
)

func TestFiniteBaseProjectionDoesNotDuplicateNativeOccupancy(t *testing.T) {
	data, err := os.ReadFile("../../scenarios/economy-e1/mapping.json")
	if err != nil {
		t.Fatal(err)
	}
	var mapping Mapping
	if err := json.Unmarshal(data, &mapping); err != nil {
		t.Fatal(err)
	}
	base := mapping.Apply(Entity{Kind: "structure", Type: "terran_command_center", Owner: 1})
	if !base.Destructible || !base.Combat.Targetable || base.Collision.Blocks || base.Combat.Health != 1500 {
		t.Fatalf("native base projection has duplicate or missing target geometry: %+v", base)
	}
	ordinary := mapping.Apply(Entity{Kind: "large_scenery", Type: "rct2.scenery_large.tbl1"})
	if !ordinary.Collision.Blocks {
		t.Fatal("ordinary park collision was relaxed")
	}
}

func TestResourceBindingsRequireBothNativeObservationsAndGeneration(t *testing.T) {
	s, err := LoadScenario("../../scenarios/economy-e1/scenario.json")
	if err != nil {
		t.Fatal(err)
	}
	ledger := NewResourceLedger(s, "session-a")
	base := ResourceObservation{SiteID: "geyser", Generation: 1, NativeID: "4",
		Type: "vespene_geyser", Owner: 11, X: 4224, Y: 3360,
		Amount: 5000, Lifecycle: "deposit"}
	if _, ok := ledger.Observe("publisher", base); ok {
		t.Fatal("published one-sided binding")
	}
	other := base
	other.NativeID = "41" // each participant owns its observed BWAPI ID
	if state, ok := ledger.Observe("controller", other); !ok || state.PublisherNativeID != "4" || state.ControllerNativeID != "41" {
		t.Fatalf("native pair was not confirmed: %+v %v", state, ok)
	}
	refinery := base
	refinery.Generation = 2
	refinery.Type, refinery.Owner, refinery.Lifecycle = "terran_refinery", 1, "refinery"
	refinery.Amount = 5000
	if _, ok := ledger.Observe("publisher", refinery); ok {
		t.Fatal("published replacement before controller")
	}
	other = refinery
	other.NativeID = "41"
	if _, ok := ledger.Observe("controller", other); !ok {
		t.Fatal("same native ID refinery transition lost")
	}
	restored := base
	restored.Generation, restored.NativeID = 3, "274"
	if _, ok := ledger.Observe("publisher", restored); ok {
		t.Fatal("published restoration before controller")
	}
	other = restored
	other.NativeID = "275"
	if state, ok := ledger.Observe("controller", other); !ok || state.PublisherNativeID != "274" {
		t.Fatal("new geyser ID not bound")
	}
	if _, ok := ledger.Observe("publisher", base); ok {
		t.Fatal("stale native ID accepted")
	}
	wrong := restored
	wrong.X++
	if _, ok := ledger.Observe("publisher", wrong); ok {
		t.Fatal("proximity substituted for exact authored site")
	}
}
