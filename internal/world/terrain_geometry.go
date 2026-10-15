package world

import "fmt"

// CornerHeights returns the corners at (0,0), (32,0), (32,32), (0,32)
// in tile-local X/Y and world Z units, following OpenRCT2 TileElementHeight.
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
	// OpenRCT2's named north corner is at (32,32), south at (0,0),
	// east at (32,0), and west at (0,32). Use map coordinates for edges.
	for index, bit := range [4]int{4, 2, 1, 8} {
		corners[index] = t.Height
		if slope&bit != 0 {
			corners[index] += 16
		}
	}
	// A steep corner has one quarter two land-height steps above its base.
	switch slope {
	case 23:
		corners[1] += 16
	case 27:
		corners[2] += 16
	case 29:
		corners[3] += 16
	case 30:
		corners[0] += 16
	}
	return corners, nil
}

func (t Terrain) ValidateGeometry() error {
	ground, err := t.CornerHeights()
	if err != nil {
		return err
	}
	if t.Water < 0 || len(t.GroundPaths) > 1 || len(t.PathLayers) > 16 {
		return fmt.Errorf("water or path layer limit")
	}
	if len(t.GroundPaths) != 0 && len(t.PathLayers) != 0 {
		return fmt.Errorf("conflicting legacy and layered paths")
	}
	for _, path := range t.GroundPaths {
		pathCorners, err := pathCornerHeights(path.BaseHeight, path.SlopeDirection)
		if err != nil {
			return err
		}
		if ground != pathCorners {
			return fmt.Errorf("path does not follow the single ground surface: ground=%v path=%v", ground, pathCorners)
		}
	}
	for i, path := range t.PathLayers {
		if path.OccupiedQuadrants < 1 || path.OccupiedQuadrants > 15 ||
			path.ClearanceHeight <= path.BaseHeight || path.ClearanceHeight > 32768 {
			return fmt.Errorf("invalid path layer geometry")
		}
		corners, err := pathCornerHeights(path.BaseHeight, path.SlopeDirection)
		if err != nil {
			return err
		}
		above, below := false, false
		for j, z := range corners {
			if z > ground[j] {
				above = true
			}
			if z < ground[j] {
				below = true
			}
		}
		if above && below {
			return fmt.Errorf("path crosses unsupported terrain surface")
		}
		for _, prior := range t.PathLayers[:i] {
			if prior.BaseHeight == path.BaseHeight && sameSlopeDirection(prior.SlopeDirection, path.SlopeDirection) &&
				prior.OccupiedQuadrants&path.OccupiedQuadrants != 0 {
				return fmt.Errorf("duplicate path layer")
			}
		}
	}
	return nil
}

func sameSlopeDirection(a, b *int) bool {
	if a == nil || b == nil {
		return a == nil && b == nil
	}
	return *a == *b
}

func pathCornerHeights(base int, slopeDirection *int) ([4]int, error) {
	pathSlope := 0
	if slopeDirection != nil {
		if *slopeDirection < 0 || *slopeDirection > 3 {
			return [4]int{}, fmt.Errorf("invalid path slope direction %d", *slopeDirection)
		}
		// Match OpenRCT2 kPathSlopeToLandSlope's elevation pattern for
		// each path direction; path bits and surface slope bits use different
		// encodings.
		pathSlope = [4]int{12, 9, 3, 6}[*slopeDirection]
	}
	pathTerrain := Terrain{Height: base, Slope: pathSlope}
	pathCorners, err := pathTerrain.CornerHeights()
	if err != nil {
		return [4]int{}, fmt.Errorf("invalid path: %w", err)
	}
	return pathCorners, nil
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
