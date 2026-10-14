package world

import "testing"

func TestZoneSelectionUsesNativeClearanceOccupancyAndReservations(t *testing.T) {
	mask := NavigationMask{Width: 128, Height: 128, Bits: make([]byte, 128*4*128*4/8)}
	transform, err := Fit(64, 64, 128, 128)
	if err != nil {
		t.Fatal(err)
	}
	zone := SpawnZone{Tiles: [][2]int{{43, 56}, {44, 56}, {45, 56}, {46, 56}}}
	first := Point{X: 43*32 + 16, Y: 56*32 + 16}
	nx, ny := transform.X(first.X), transform.Y(first.Y)
	if got, ok := SelectZonePosition(zone, mask, transform, nil, nil); !ok || got != first {
		t.Fatalf("first authored tile: %v %v", got, ok)
	}
	for y := ny - 12; y <= ny+12; y += 8 {
		mask.set(nx/8, y/8, true)
	}
	occupied := []NativeOccupant{{X: transform.X(44*32 + 16), Y: transform.Y(56*32 + 16)}}
	reserved := []Point{{X: 45*32 + 16, Y: 56*32 + 16}}
	want := Point{X: 46*32 + 16, Y: 56*32 + 16}
	if got, ok := SelectZonePosition(zone, mask, transform, occupied, reserved); !ok || got != want {
		t.Fatalf("fallback tile: %v %v", got, ok)
	}
	reserved = append(reserved, want)
	if _, ok := SelectZonePosition(zone, mask, transform, occupied, reserved); ok {
		t.Fatal("occupied zone accepted")
	}
}
