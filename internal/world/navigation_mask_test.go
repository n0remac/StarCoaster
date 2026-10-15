package world

import "testing"

func TestHeightAwareTrackClearanceAndQuadrants(t *testing.T) {
	base := exampleEntity("openrct2:ride:17#1")
	base.Collision = Collision{Blocks: true, Mode: "height_aware"}
	base.Collision.Volumes = []CollisionVolume{{Rect: Rect{64, 96, 32, 32}, BaseZ: 144,
		ClearanceZ: 152, OccupiedQuadrants: 15, Classification: "approximate"}}
	terrain := []Terrain{{X: 2, Y: 3, Height: 112, Walkable: true}}
	high := navFor(t, 8, 8, 12, 12, terrain, []Entity{base})
	// Centering adds two build tiles in each dimension.
	if high.BlockedWalk(17, 21) {
		t.Fatal("track exactly 32 Z above flat land blocked passage")
	}
	base.Collision.Volumes[0].BaseZ = 143
	low := navFor(t, 8, 8, 12, 12, terrain, []Entity{base})
	if !low.BlockedWalk(17, 21) || high.Hash == low.Hash {
		t.Fatal("low track did not block")
	}
	base.Collision.Volumes[0].OccupiedQuadrants = 4 // NE
	quarter := navFor(t, 8, 8, 12, 12, terrain, []Entity{base})
	if !quarter.BlockedWalk(18, 20) || quarter.BlockedWalk(17, 21) {
		t.Fatal("rotated quarter occupancy projected onto the wrong walk cells")
	}
	base.Collision.Volumes = nil
	empty := navFor(t, 8, 8, 12, 12, terrain, []Entity{base})
	if empty.BlockedWalk(17, 21) {
		t.Fatal("empty height-aware collision fell back to logical footprint")
	}
}

func TestHeightAwareSlopedGroundAndOrder(t *testing.T) {
	base := exampleEntity("openrct2:ride:17#1")
	base.Collision = Collision{Blocks: true, Mode: "height_aware", Volumes: []CollisionVolume{
		{Rect: Rect{64, 96, 32, 32}, BaseZ: 152, ClearanceZ: 168, OccupiedQuadrants: 15, Classification: "physical"},
		{Rect: Rect{96, 96, 32, 32}, BaseZ: 180, ClearanceZ: 196, OccupiedQuadrants: 15, Classification: "physical"},
	}}
	terrain := []Terrain{{X: 2, Y: 3, Height: 112, Slope: 3, Walkable: true},
		{X: 3, Y: 3, Height: 128, Walkable: true}}
	a := navFor(t, 8, 8, 8, 8, terrain, []Entity{base})
	if a.BlockedWalk(8, 13) || !a.BlockedWalk(11, 13) || a.BlockedWalk(13, 13) {
		t.Fatal("local slope heights or overhead boundary are wrong")
	}
	base.Collision.Volumes[0], base.Collision.Volumes[1] = base.Collision.Volumes[1], base.Collision.Volumes[0]
	b := navFor(t, 8, 8, 8, 8, terrain, []Entity{base})
	if a.Hash != b.Hash {
		t.Fatal("equivalent collision order changed mask")
	}
}

func TestNavigationTraceUsesAuthoritativeProjection(t *testing.T) {
	r := NewRegistry()
	e := exampleEntity("openrct2:ride:17#1")
	e.Collision = Collision{Blocks: true, Mode: "height_aware", Volumes: []CollisionVolume{{
		Rect: Rect{64, 96, 32, 32}, BaseZ: 112, ClearanceZ: 120,
		OccupiedQuadrants: 15, Classification: "approximate", Source: "track:0:0:0"}}}
	if err := r.Replace("trace", 1, 8, 8, []Entity{e},
		[]Terrain{{X: 2, Y: 3, Height: 112, Walkable: true}}); err != nil {
		t.Fatal(err)
	}
	transform, _ := Fit(8, 8, 8, 8)
	normal, err := DeriveNavigation(r, transform, 8, 8)
	if err != nil {
		t.Fatal(err)
	}
	traced, err := DeriveNavigationTrace(r, transform, 8, 8)
	if err != nil {
		t.Fatal(err)
	}
	index, _ := traced.index(8, 12)
	if traced.Hash != normal.Hash || len(traced.Causes[index]) != 1 ||
		traced.Causes[index][0] != e.ID+"/track:0:0:0" {
		t.Fatal("diagnostic cause diverged from navigation projection")
	}
}

func TestRaisedPathTraceRecordsSlabApproximation(t *testing.T) {
	r := NewRegistry()
	rule := Terrain{X: 2, Y: 3, Height: 112, Walkable: true, PathLayers: []TerrainPathLayer{{
		BaseHeight: 136, ClearanceHeight: 168, OccupiedQuadrants: 15,
	}}}
	if err := r.Replace("path-trace", 1, 8, 8, nil, []Terrain{rule}); err != nil {
		t.Fatal(err)
	}
	transform, _ := Fit(8, 8, 8, 8)
	trace, err := DeriveNavigationTrace(r, transform, 8, 8)
	if err != nil {
		t.Fatal(err)
	}
	index, _ := trace.index(8, 12)
	if !trace.BlockedWalk(8, 12) || len(trace.Causes[index]) == 0 ||
		trace.Causes[index][0] != "path:2:3:136:slab_approx" {
		t.Fatal("raised path obstruction lacks its approximation reason")
	}
}

func navFor(t *testing.T, width, height, bwWidth, bwHeight int, cells []Terrain, entities []Entity) NavigationMask {
	t.Helper()
	r := NewRegistry()
	if err := r.Replace("nav", 1, width, height, entities, cells); err != nil {
		t.Fatal(err)
	}
	transform, err := Fit(width, height, bwWidth, bwHeight)
	if err != nil {
		t.Fatal(err)
	}
	m, err := DeriveNavigation(r, transform, bwWidth, bwHeight)
	if err != nil {
		t.Fatal(err)
	}
	return m
}

func TestNavigationMaskBlocksPaddingAndKeepsParkScale(t *testing.T) {
	m := navFor(t, 64, 64, 256, 256, nil, nil)
	if len(m.Bits) != 131072 || !m.BlockedWalk(0, 0) || !m.BlockedPixel(95*32+16, 100*32+16) ||
		m.BlockedPixel(96*32+16, 96*32+16) || m.BlockedPixel(159*32+16, 159*32+16) ||
		!m.BlockedPixel(160*32+16, 159*32+16) {
		t.Fatal("centered park padding or 1:1 coordinates are wrong")
	}
	other := navFor(t, 64, 64, 256, 256, nil, nil)
	if m.Hash != other.Hash {
		t.Fatal("deterministic navigation hashes differ")
	}
}

func TestNavigationMaskRoutesThroughSlopeAndBlocksCliff(t *testing.T) {
	low := Terrain{X: 0, Height: 112, Walkable: true}
	ramp := Terrain{X: 1, Height: 112, Slope: 3, Walkable: true}
	high := Terrain{X: 2, Height: 128, Walkable: true}
	m := navFor(t, 3, 1, 3, 1, []Terrain{low, ramp, high}, nil)
	for _, x := range []int{3, 4, 7, 8} {
		if m.BlockedWalk(x, 1) {
			t.Fatalf("connected slope blocked at walk cell %d", x)
		}
	}
	cliff := navFor(t, 4, 1, 4, 1, []Terrain{low,
		{X: 1, Height: 128, Walkable: true}, {X: 2, Height: 128, Walkable: true},
		{X: 3, Height: 128, Walkable: true}}, nil)
	if !cliff.BlockedWalk(3, 1) || !cliff.BlockedWalk(4, 1) ||
		!cliff.BlockedWalk(7, 1) || cliff.BlockedWalk(9, 1) {
		t.Fatal("cliff transition or elevated flat surface was masked incorrectly")
	}
	water := navFor(t, 2, 1, 2, 1, []Terrain{low,
		{X: 1, Height: 112, Water: 128, Walkable: false}}, nil)
	if !water.BlockedWalk(6, 1) {
		t.Fatal("water remains traversable")
	}
}

func TestNavigationMaskDemolitionKeepsPermanentBarrier(t *testing.T) {
	wall := exampleEntity("openrct2:wall:1#1")
	wall.Kind = "wall"
	wall.Collision.Blocks = true
	wall.Geometry.Cells = []Point{{2, 0}}
	wall.Geometry.Rects = []Rect{{72, 8, 8, 16}}
	wall.Position = Point{72, 8}
	low := Terrain{X: 0, Height: 112, Walkable: true}
	high := Terrain{X: 1, Height: 128, Walkable: true}
	r := NewRegistry()
	if err := r.Replace("nav", 1, 4, 1, []Entity{wall}, []Terrain{low, high,
		{X: 2, Height: 128, Walkable: true}, {X: 3, Height: 128, Walkable: true}}); err != nil {
		t.Fatal(err)
	}
	transform, _ := Fit(4, 1, 4, 1)
	before, err := DeriveNavigation(r, transform, 4, 1)
	if err != nil {
		t.Fatal(err)
	}
	r.Destroyed[wall.ID] = true
	after, err := DeriveNavigation(r, transform, 4, 1)
	if err != nil {
		t.Fatal(err)
	}
	if before.Hash == after.Hash || !after.BlockedWalk(3, 1) || !after.BlockedWalk(4, 1) ||
		!after.BlockedWalk(7, 1) || after.BlockedWalk(9, 1) {
		t.Fatal("demolition removed a permanent cliff or failed to clear the wall")
	}
}
