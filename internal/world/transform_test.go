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
