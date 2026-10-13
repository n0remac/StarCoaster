package world

import "testing"

func TestFitAndGeometryConversion(t *testing.T) {
	transform, err := Fit(256, 256, 256, 256)
	if err != nil { t.Fatal(err) }
	e := exampleEntity("openrct2:ride:17#1")
	converted := transform.Entity(e)
	if converted.ID != e.ID || converted.Position != (Point{64, 96}) || converted.Geometry.Rects[0] != (Rect{64, 96, 64, 32}) {
		t.Fatalf("bad transformed entity: %+v", converted)
	}
	if e.Position != (Point{64, 96}) || e.Geometry.Rects[0].Width != 64 {
		t.Fatal("conversion mutated park entity")
	}
	if transform.InversePixel(converted.Position.X) != e.Position.X {
		t.Fatal("inverse actor coordinate differs")
	}
	cells := transform.Terrain([]Terrain{{X: 0, Y: 0, Height: 8}, {X: 1, Y: 0, Height: 16}})
	if len(cells) != 2 || cells[1].X != 1 {
		t.Fatalf("terrain cells were distorted: %+v", cells)
	}
}

func TestCenteredParkCoordinatesRoundTrip(t *testing.T) {
	transform, err := Fit(64, 64, 256, 256)
	if err != nil { t.Fatal(err) }
	if transform.Numerator != 1 || transform.Denominator != 1 || transform.OffsetX != 96 || transform.OffsetY != 96 {
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
	if converted.Position != (Point{5056, 5056}) || converted.Geometry.Cells[0] != (Point{159, 159}) ||
		converted.Geometry.Rects[0] != (Rect{5056, 5056, 64, 64}) {
		t.Fatalf("boundary object was distorted: %+v", converted)
	}
	terrain := transform.Terrain([]Terrain{{X: 0, Y: 0}, {X: 63, Y: 63}})
	if len(terrain) != 2 || terrain[0].X != 96 || terrain[0].Y != 96 || terrain[1].X != 159 || terrain[1].Y != 159 {
		t.Fatalf("terrain offset differs from entities: %+v", terrain)
	}
}

func TestFitSupportedDimensions(t *testing.T) {
	for _, size := range [][2]int{{64,64},{128,128},{256,256},{48,96},{255,128}} {
		tr, err := Fit(size[0], size[1], 256, 256)
		if err != nil { t.Fatalf("%v: %v", size, err) }
		for _, p := range []Point{{0,0},{size[0]*32-1,size[1]*32-1}} {
			if tr.InverseX(tr.X(p.X)) != p.X || tr.InverseY(tr.Y(p.Y)) != p.Y { t.Fatalf("%v: round trip %+v",size,p) }
		}
	}
	for _, size := range [][2]int{{257,256},{256,257},{129,256},{0,64}} {
		if _, err := Fit(size[0],size[1],128,256); err == nil { t.Fatalf("accepted unsupported %v",size) }
	}
}
