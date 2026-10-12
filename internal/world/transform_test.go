package world

import "testing"

func TestFitAndGeometryConversion(t *testing.T) {
	transform := Fit(256, 256, 128, 128)
	if transform.Numerator != 128 || transform.Denominator != 256 {
		t.Fatalf("unexpected scale: %+v", transform)
	}
	e := exampleEntity("openrct2:ride:17#1")
	converted := transform.Entity(e)
	if converted.ID != e.ID || converted.Position != (Point{32, 48}) || converted.Geometry.Rects[0] != (Rect{32, 48, 32, 16}) {
		t.Fatalf("bad transformed entity: %+v", converted)
	}
	if e.Position != (Point{64, 96}) || e.Geometry.Rects[0].Width != 64 {
		t.Fatal("conversion mutated park entity")
	}
	if transform.InversePixel(converted.Position.X) != e.Position.X {
		t.Fatal("inverse actor coordinate differs")
	}
	cells := transform.Terrain([]Terrain{{X: 0, Y: 0, Height: 8}, {X: 1, Y: 0, Height: 16}})
	if len(cells) != 1 || cells[0].Height != 16 {
		t.Fatalf("terrain cells were not merged: %+v", cells)
	}
}

func TestCenteredParkCoordinatesRoundTrip(t *testing.T) {
	transform := Fit(64, 64, 128, 128)
	if transform.Numerator != 1 || transform.Denominator != 1 || transform.OffsetX != 32 || transform.OffsetY != 32 {
		t.Fatalf("64 tile park must be centered without scaling: %+v", transform)
	}
	for _, p := range []Point{{0, 0}, {16, 32}, {2047, 2047}} {
		if transform.InverseX(transform.X(p.X)) != p.X || transform.InverseY(transform.Y(p.Y)) != p.Y {
			t.Fatalf("coordinate round trip failed at %+v", p)
		}
	}
	e := exampleEntity("openrct2:ride:17#1")
	e.Position = Point{1984, 1984}
	e.Geometry.Cells = []Point{{63, 63}}
	e.Geometry.Rects = []Rect{{1984, 1984, 64, 64}}
	converted := transform.Entity(e)
	if converted.Position != (Point{3008, 3008}) || converted.Geometry.Cells[0] != (Point{95, 95}) ||
		converted.Geometry.Rects[0] != (Rect{3008, 3008, 64, 64}) {
		t.Fatalf("boundary object was distorted: %+v", converted)
	}
	terrain := transform.Terrain([]Terrain{{X: 0, Y: 0}, {X: 63, Y: 63}})
	if len(terrain) != 2 || terrain[0].X != 32 || terrain[0].Y != 32 || terrain[1].X != 95 || terrain[1].Y != 95 {
		t.Fatalf("terrain offset differs from entities: %+v", terrain)
	}
}
