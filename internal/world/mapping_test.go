package world

import (
	"encoding/json"
	"os"
	"testing"
)

func TestMappingBoundsSelectOnlyAuthoredParkTargets(t *testing.T) {
	bounds := [4]int{71, 73, 141, 144}
	mapping := Mapping{Rules: []Rule{
		{Kind: "large_scenery", Destructible: pointer(false), Targetable: pointer(false), Blocks: pointer(true)},
		{Kind: "large_scenery", WithinTiles: &bounds, Destructible: pointer(true), Targetable: pointer(true)},
	}}
	inside := Entity{Kind: "large_scenery", Geometry: Geometry{Cells: []Point{{X: 90, Y: 131}, {X: 92, Y: 133}}}}
	outside := Entity{Kind: "large_scenery", Geometry: Geometry{Cells: []Point{{X: 90, Y: 47}}}}
	edge := Entity{Kind: "large_scenery", Geometry: Geometry{Cells: []Point{{X: 141, Y: 100}, {X: 142, Y: 100}}}}
	for _, test := range []struct {
		entity Entity
		target bool
	}{{inside, true}, {outside, false}, {edge, false}} {
		got := mapping.Apply(test.entity)
		if got.Combat.Targetable != test.target || got.Collision.Blocks != true {
			t.Fatalf("bounds selected wrong target: %+v", got)
		}
	}
}

func TestGuestsStayOutsideNativeCombatTargets(t *testing.T) {
	guest := Entity{Kind: "guest", Type: "park_guest", Geometry: Geometry{Cells: []Point{{X: 118, Y: 127}}}}
	data, err := os.ReadFile("../../scenarios/mt-zergling/mapping.json")
	if err != nil {
		t.Fatal(err)
	}
	var mtZergling Mapping
	if err := json.Unmarshal(data, &mtZergling); err != nil {
		t.Fatal(err)
	}
	for _, mapping := range []Mapping{DefaultMapping(), mtZergling} {
		got := mapping.Apply(guest)
		if got.Destructible || got.Combat.Targetable || got.Collision.Blocks {
			t.Fatalf("guest became a combat target or obstacle: %+v", got)
		}
	}
}
