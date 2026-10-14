package world

import "testing"

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
