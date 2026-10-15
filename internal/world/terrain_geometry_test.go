package world

import (
	"strings"
	"testing"
)

func direction(value int) *int { return &value }

func TestTerrainGeometryMatchesNativeSlopeTable(t *testing.T) {
	for _, test := range []struct {
		name    string
		terrain Terrain
		want    [4]int
	}{
		{"flat", Terrain{Height: 112}, [4]int{112, 112, 112, 112}},
		{"map origin corner", Terrain{Height: 112, Slope: 4}, [4]int{128, 112, 112, 112}},
		{"east side", Terrain{Height: 112, Slope: 3}, [4]int{112, 128, 128, 112}},
		{"opposite side", Terrain{Height: 112, Slope: 12}, [4]int{128, 112, 112, 128}},
		{"south side", Terrain{Height: 112, Slope: 9}, [4]int{112, 112, 128, 128}},
		{"north side", Terrain{Height: 112, Slope: 6}, [4]int{128, 128, 112, 112}},
		{"steep corner", Terrain{Height: 112, Slope: 23}, [4]int{128, 144, 128, 112}},
	} {
		t.Run(test.name, func(t *testing.T) {
			got, err := test.terrain.CornerHeights()
			if err != nil || got != test.want {
				t.Fatalf("corners=%v error=%v, want %v", got, err, test.want)
			}
		})
	}
}

func TestTerrainGroundPathsAndUnsupportedShapes(t *testing.T) {
	for _, terrain := range []Terrain{
		{Height: 112, Slope: 12, GroundPaths: []TerrainPath{{BaseHeight: 112, SlopeDirection: direction(0)}}},
		{Height: 112, Slope: 9, GroundPaths: []TerrainPath{{BaseHeight: 112, SlopeDirection: direction(1)}}},
		{Height: 112, Slope: 3, GroundPaths: []TerrainPath{{BaseHeight: 112, SlopeDirection: direction(2)}}},
		{Height: 112, Slope: 6, GroundPaths: []TerrainPath{{BaseHeight: 112, SlopeDirection: direction(3)}}},
		{Height: 128, GroundPaths: []TerrainPath{{BaseHeight: 128}}},
		{Height: 112, Water: 128, Walkable: false},
	} {
		if err := terrain.ValidateGeometry(); err != nil {
			t.Fatalf("valid geometry rejected: %+v: %v", terrain, err)
		}
	}
	for _, terrain := range []Terrain{
		{Height: 112, Slope: 16},
		{Height: 112, Slope: 64},
		{Height: 112, Slope: 3, GroundPaths: []TerrainPath{{BaseHeight: 112}}},
		{Height: 112, Slope: 9, GroundPaths: []TerrainPath{{BaseHeight: 112, SlopeDirection: direction(3)}}},
		{Height: 112, GroundPaths: []TerrainPath{{BaseHeight: 128}}},
		{Height: 112, GroundPaths: []TerrainPath{{BaseHeight: 112}, {BaseHeight: 112}}},
		{Height: 112, GroundPaths: []TerrainPath{{BaseHeight: 112, SlopeDirection: direction(4)}}},
	} {
		if err := terrain.ValidateGeometry(); err == nil {
			t.Fatalf("ambiguous geometry accepted: %+v", terrain)
		}
	}
	registry := NewRegistry()
	if err := registry.Replace("session", 1, 2, 1, nil,
		[]Terrain{{X: 0, Y: 0, Height: 112, Slope: 16}}); err == nil || !strings.Contains(err.Error(), "unsupported_terrain") {
		t.Fatalf("registry did not report unsupported terrain: %v", err)
	}
}

func TestLayeredPathsPreserveGroundRouteAndRejectConflict(t *testing.T) {
	ground := TerrainPathLayer{BaseHeight: 112, ClearanceHeight: 144, OccupiedQuadrants: 15}
	high := TerrainPathLayer{BaseHeight: 144, ClearanceHeight: 176, OccupiedQuadrants: 15}
	cell := Terrain{X: 0, Y: 0, Height: 112, Walkable: true, PathLayers: []TerrainPathLayer{ground, high}}
	if err := cell.ValidateGeometry(); err != nil {
		t.Fatal(err)
	}
	clear := navFor(t, 1, 1, 1, 1, []Terrain{cell}, nil)
	if clear.BlockedWalk(1, 1) {
		t.Fatal("high bridge blocked ground path")
	}
	cell.PathLayers[1].BaseHeight = 136
	low := navFor(t, 1, 1, 1, 1, []Terrain{cell}, nil)
	if !low.BlockedWalk(1, 1) || low.Hash == clear.Hash {
		t.Fatal("low overhead slab did not block")
	}
	cell.PathLayers[1].BaseHeight = 96
	sub := navFor(t, 1, 1, 1, 1, []Terrain{cell}, nil)
	if sub.BlockedWalk(1, 1) {
		t.Fatal("subsurface path became a ground obstruction")
	}
	cell.PathLayers = []TerrainPathLayer{ground, ground}
	if cell.ValidateGeometry() == nil {
		t.Fatal("duplicate path layer accepted")
	}
	cell.PathLayers = []TerrainPathLayer{ground}
	cell.GroundPaths = []TerrainPath{{BaseHeight: 112}}
	if cell.ValidateGeometry() == nil {
		t.Fatal("legacy and layered paths combined")
	}
}

func TestTerrainEdgesDistinguishSlopesAndCliffs(t *testing.T) {
	low := Terrain{Height: 112, Walkable: true}
	high := Terrain{Height: 128, Walkable: true}
	ramp := Terrain{Height: 112, Slope: 3, Walkable: true}
	opposite := Terrain{Height: 112, Slope: 12, Walkable: true}
	for _, test := range []struct {
		name      string
		from, to  Terrain
		dx, dy    int
		connected bool
	}{
		{"flat", low, low, 1, 0, true},
		{"slope entry", low, ramp, 1, 0, true},
		{"slope exit", ramp, high, 1, 0, true},
		{"south slope entry", low, Terrain{Height: 112, Slope: 9, Walkable: true}, 0, 1, true},
		{"south slope exit", Terrain{Height: 112, Slope: 9, Walkable: true}, high, 0, 1, true},
		{"north slope entry", high, Terrain{Height: 112, Slope: 6, Walkable: true}, 0, 1, true},
		{"north slope exit", Terrain{Height: 112, Slope: 6, Walkable: true}, low, 0, 1, true},
		{"gradual second slope", ramp, Terrain{Height: 128, Slope: 3, Walkable: true}, 1, 0, true},
		{"opposite slope", low, opposite, 1, 0, false},
		{"vertical cliff", low, high, 1, 0, false},
		{"hilltop south cliff", low, high, 0, 1, false},
		{"water", low, Terrain{Height: 112, Water: 128, Walkable: false}, 1, 0, false},
	} {
		t.Run(test.name, func(t *testing.T) {
			connected, err := TerrainEdgeConnected(test.from, test.to, test.dx, test.dy)
			if err != nil || connected != test.connected {
				t.Fatalf("connected=%t error=%v, want %t", connected, err, test.connected)
			}
		})
	}
	if _, err := TerrainEdgeConnected(low, high, -1, 0); err == nil {
		t.Fatal("unsupported boundary direction accepted")
	}
}
