package world

// NativeOccupant is a living native actor's center in OpenBW pixels. Callers
// must supply positions from a complete authoritative combat snapshot.
type NativeOccupant struct {
	X, Y int
}

// SelectZonePosition returns a park-pixel center in authored tile order. The
// existing transform is used only for native bounds, navigation and occupancy;
// pumpSpawns performs the single transform on the eventual request. This is a
// preliminary clearance filter; OpenBW validates the requested unit's actual
// BWAPI dimensions and reports any placement rejection.
func SelectZonePosition(zone SpawnZone, mask NavigationMask, transform Transform,
	occupants []NativeOccupant, reserved []Point) (Point, bool) {
	const half = 12 // minimum center clearance; OpenBW checks the native footprint
	for _, tile := range zone.Tiles {
		park := Point{X: tile[0]*32 + 16, Y: tile[1]*32 + 16}
		x, y := transform.X(park.X), transform.Y(park.Y)
		if x < half || y < half || x+half >= mask.Width*32 || y+half >= mask.Height*32 {
			continue
		}
		blocked := false
		for dy := -half; dy <= half && !blocked; dy += 4 {
			for dx := -half; dx <= half; dx += 4 {
				if mask.BlockedPixel(x+dx, y+dy) {
					blocked = true
					break
				}
			}
		}
		if blocked {
			continue
		}
		for _, unit := range occupants {
			if absInt(x-unit.X) < 28 && absInt(y-unit.Y) < 28 {
				blocked = true
				break
			}
		}
		if blocked {
			continue
		}
		for _, previous := range reserved {
			if absInt(park.X-previous.X) < 28 && absInt(park.Y-previous.Y) < 28 {
				blocked = true
				break
			}
		}
		if !blocked {
			return park, true
		}
	}
	return Point{}, false
}

func absInt(value int) int {
	if value < 0 {
		return -value
	}
	return value
}
