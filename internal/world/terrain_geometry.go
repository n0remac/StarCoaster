package world

import "fmt"

// CornerHeights returns OpenRCT2's north, east, south, west quarter heights in
// world Z units. It follows GetSlopeCornerHeights in OpenRCT2's Slope.cpp.
// The low four slope bits encode raised quarters; the diagonal bit is valid
// only for the four native steep-corner shapes. Bit 5 is a scenery support flag.
func (t Terrain) CornerHeights() ([4]int, error) {
	var corners [4]int
	if t.Height < 0 || t.Height > 32768 || t.Height%8 != 0 || t.Slope < 0 || t.Slope > 63 {
		return corners, fmt.Errorf("invalid surface height or slope: height=%d slope=%d", t.Height, t.Slope)
	}
	slope := t.Slope & 31
	if slope&16 != 0 {
		switch slope {
		case 23, 27, 29, 30:
		default:
			return corners, fmt.Errorf("ambiguous diagonal slope %d", t.Slope)
		}
	}
	// OpenRCT2's relative table maps the raised-corner bits to these native
	// quarter names. The order here matches TileCornersZ, not screen rotation.
	for index, bit := range [4]int{1, 8, 4, 2} {
		corners[index] = t.Height
		if slope&bit != 0 {
			corners[index] += 16
		}
	}
	// A steep corner has one quarter two land-height steps above its base.
	switch slope {
	case 23:
		corners[3] += 16
	case 27:
		corners[0] += 16
	case 29:
		corners[1] += 16
	case 30:
		corners[2] += 16
	}
	return corners, nil
}

func (t Terrain) ValidateGeometry() error {
	ground, err := t.CornerHeights()
	if err != nil {
		return err
	}
	if t.Water < 0 || len(t.GroundPaths) > 1 {
		return fmt.Errorf("water or overlapping ground paths")
	}
	if len(t.GroundPaths) == 0 {
		return nil
	}
	path := t.GroundPaths[0]
	pathSlope := 0
	if path.SlopeDirection != nil {
		if *path.SlopeDirection < 0 || *path.SlopeDirection > 3 {
			return fmt.Errorf("invalid path slope direction %d", *path.SlopeDirection)
		}
		// Match OpenRCT2 MapHeightFromSlope's actual elevation pattern for
		// each path direction; path bits and surface slope bits use different
		// encodings.
		pathSlope = [4]int{3, 6, 12, 9}[*path.SlopeDirection]
	}
	pathTerrain := Terrain{Height: path.BaseHeight, Slope: pathSlope}
	pathCorners, err := pathTerrain.CornerHeights()
	if err != nil {
		return fmt.Errorf("invalid path: %w", err)
	}
	if ground != pathCorners {
		return fmt.Errorf("path does not follow the single ground surface: ground=%v path=%v", ground, pathCorners)
	}
	return nil
}

// TerrainEdgeConnected compares both native quarter heights on a shared edge.
// dx=1 compares a tile to its eastern neighbor; dy=1 compares its southern
// neighbor. A diagonal step requires both cardinal edges in navigation.
func TerrainEdgeConnected(from, to Terrain, dx, dy int) (bool, error) {
	if (dx != 1 || dy != 0) && (dx != 0 || dy != 1) {
		return false, fmt.Errorf("unsupported terrain edge direction %d,%d", dx, dy)
	}
	if err := from.ValidateGeometry(); err != nil {
		return false, err
	}
	if err := to.ValidateGeometry(); err != nil {
		return false, err
	}
	if !from.Walkable || !to.Walkable || from.Water > 0 || to.Water > 0 {
		return false, nil
	}
	a, _ := from.CornerHeights()
	b, _ := to.CornerHeights()
	if dx == 1 {
		return a[1] == b[0] && a[2] == b[3], nil
	}
	return a[2] == b[1] && a[3] == b[0], nil
}
