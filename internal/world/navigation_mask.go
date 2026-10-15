package world

import (
	"fmt"
	"hash/fnv"
	"time"
)

// NavigationMask is a packed 8-pixel OpenBW walk grid. Bit one is blocked.
// OpenBW remains responsible for pathfinding and unit collision on this grid.
type NavigationMask struct {
	Width, Height  int // OpenBW build tiles
	Bits           []byte
	Hash           string
	DerivationTime time.Duration    `json:"-"`
	Causes         map[int][]string `json:"-"` // populated only by the test diagnostic variant
}

func (m NavigationMask) walkWidth() int { return m.Width * 4 }

func (m NavigationMask) index(x, y int) (int, bool) {
	if x < 0 || y < 0 || x >= m.walkWidth() || y >= m.Height*4 {
		return 0, false
	}
	return y*m.walkWidth() + x, true
}

func (m NavigationMask) BlockedWalk(x, y int) bool {
	i, ok := m.index(x, y)
	return !ok || m.Bits[i>>3]&(1<<(i&7)) != 0
}

func (m NavigationMask) BlockedPixel(x, y int) bool {
	if x < 0 || y < 0 {
		return true
	}
	return m.BlockedWalk(x/8, y/8)
}

func (m NavigationMask) set(x, y int, blocked bool) {
	i, ok := m.index(x, y)
	if !ok {
		return
	}
	if blocked {
		m.Bits[i>>3] |= 1 << (i & 7)
	} else {
		m.Bits[i>>3] &^= 1 << (i & 7)
	}
}

func (m NavigationMask) setCause(x, y int, cause string) {
	m.set(x, y, true)
	if m.Causes != nil {
		index, ok := m.index(x, y)
		if ok {
			m.Causes[index] = append(m.Causes[index], cause)
		}
	}
}

func (m NavigationMask) fillTile(x, y int, blocked bool) {
	for row := 0; row < 4; row++ {
		for column := 0; column < 4; column++ {
			m.set(x*4+column, y*4+row, blocked)
		}
	}
}

func (m NavigationMask) blockEastEdge(x, y int) {
	// Native path smoothing crossed narrower masks in the live route probe.
	// Reserve the two full build tiles bordering a cliff.
	for row := 0; row < 4; row++ {
		for column := 0; column < 8; column++ {
			m.setCause(x*4+column, y*4+row, "cliff")
		}
	}
}

func (m NavigationMask) blockSouthEdge(x, y int) {
	for row := 0; row < 8; row++ {
		for column := 0; column < 4; column++ {
			m.setCause(x*4+column, y*4+row, "cliff")
		}
	}
}

func (m NavigationMask) blockRect(r Rect, source string) {
	for y := r.Y / 8; y <= (r.Y+r.Height-1)/8; y++ {
		for x := r.X / 8; x <= (r.X+r.Width-1)/8; x++ {
			m.setCause(x, y, source)
		}
	}
}

const groundUnitClearanceZ = 32

// groundHeightRange encloses the supported surface inside one native walk
// cell. Steep diagonal corners use the full tile range conservatively.
func groundHeightRange(t Terrain, localX, localY int) (int, int, error) {
	corners, err := t.CornerHeights()
	if err != nil {
		return 0, 0, err
	}
	if t.Slope&16 != 0 {
		lo, hi := corners[0], corners[0]
		for _, z := range corners[1:] {
			if z < lo {
				lo = z
			}
			if z > hi {
				hi = z
			}
		}
		return lo, hi, nil
	}
	lo, hi := 32768, -4096
	for _, p := range [4]Point{{localX, localY}, {localX + 8, localY}, {localX, localY + 8}, {localX + 8, localY + 8}} {
		// Bilinear interpolation encloses the supported planar corner heights.
		n := corners[0]*(32-p.X)*(32-p.Y) + corners[1]*p.X*(32-p.Y) +
			corners[2]*p.X*p.Y + corners[3]*(32-p.X)*p.Y
		bottom, top := n/1024, (n+1023)/1024
		if bottom < lo {
			lo = bottom
		}
		if top > hi {
			hi = top
		}
	}
	return lo, hi, nil
}

func (m NavigationMask) blockVolume(v CollisionVolume, cells []Terrain, parkWidth, parkHeight int, transform Transform, source string) error {
	r := transform.rect(v.Rect)
	for wy := r.Y / 8; wy <= (r.Y+r.Height-1)/8; wy++ {
		for wx := r.X / 8; wx <= (r.X+r.Width-1)/8; wx++ {
			if v.OccupiedQuadrants != 15 {
				// A partial mask always describes one 32-pixel source tile.
				localX, localY := wx*8-r.X, wy*8-r.Y
				quadrant := walkQuadrant(localX, localY)
				if v.OccupiedQuadrants&quadrant == 0 {
					continue
				}
			}
			x, y := wx/4-transform.OffsetX, wy/4-transform.OffsetY
			if x < 0 || y < 0 || x >= parkWidth || y >= parkHeight {
				continue
			}
			localX, localY := (wx%4)*8, (wy%4)*8
			lo, hi, err := groundHeightRange(cells[y*parkWidth+x], localX, localY)
			if err != nil {
				return err
			}
			if v.BaseZ < hi+groundUnitClearanceZ && v.ClearanceZ > lo {
				m.setCause(wx, wy, source)
			}
		}
	}
	return nil
}

func walkQuadrant(localX, localY int) int {
	if localX < 16 {
		if localY < 16 {
			return 2
		}
		return 1
	}
	if localY < 16 {
		return 4
	}
	return 8
}

func (m NavigationMask) blockRaisedPaths(cells []Terrain, parkWidth, parkHeight int, transform Transform) error {
	for y := 0; y < parkHeight; y++ {
		for x := 0; x < parkWidth; x++ {
			cell := cells[y*parkWidth+x]
			groundCorners, err := cell.CornerHeights()
			if err != nil {
				return err
			}
			for _, layer := range cell.PathLayers {
				pathCorners, err := pathCornerHeights(layer.BaseHeight, layer.SlopeDirection)
				if err != nil {
					return err
				}
				elevated := false
				for i, z := range pathCorners {
					if z > groundCorners[i] {
						elevated = true
					}
				}
				if !elevated {
					continue
				} // ground and subsurface layers do not add routes or obstacles
				pathSlope := 0
				if layer.SlopeDirection != nil {
					pathSlope = [4]int{12, 9, 3, 6}[*layer.SlopeDirection]
				}
				pathTerrain := Terrain{Height: layer.BaseHeight, Slope: pathSlope}
				for sy := 0; sy < 4; sy++ {
					for sx := 0; sx < 4; sx++ {
						localX, localY := sx*8, sy*8
						if layer.OccupiedQuadrants&walkQuadrant(localX, localY) == 0 {
							continue
						}
						groundLo, groundHi, err := groundHeightRange(cell, localX, localY)
						if err != nil {
							return err
						}
						pathLo, pathHi, err := groundHeightRange(pathTerrain, localX, localY)
						if err != nil {
							return err
						}
						if pathLo < groundHi+groundUnitClearanceZ && pathHi+8 > groundLo {
							m.setCause((x+transform.OffsetX)*4+sx, (y+transform.OffsetY)*4+sy,
								fmt.Sprintf("path:%d:%d:%d", x, y, layer.BaseHeight))
						}
					}
				}
			}
		}
	}
	return nil
}

// DeriveNavigation is the only world-to-native collision derivation. Missing
// cells in a partial export are blocked; an empty legacy export means flat
// ground inside the park. Padding outside the centered park stays blocked.
func DeriveNavigation(r *Registry, transform Transform, bwWidth, bwHeight int) (NavigationMask, error) {
	return deriveNavigation(r, transform, bwWidth, bwHeight, false)
}

// DeriveNavigationTrace uses the same projection and records why each cell
// was blocked. It is reserved for ignored test artifacts.
func DeriveNavigationTrace(r *Registry, transform Transform, bwWidth, bwHeight int) (NavigationMask, error) {
	return deriveNavigation(r, transform, bwWidth, bwHeight, true)
}

func deriveNavigation(r *Registry, transform Transform, bwWidth, bwHeight int, trace bool) (NavigationMask, error) {
	started := time.Now()
	if r == nil || r.Width < 1 || r.Height < 1 || bwWidth < r.Width || bwHeight < r.Height ||
		bwWidth > 256 || bwHeight > 256 || transform.Numerator != 1 || transform.Denominator != 1 ||
		transform.OffsetX != (bwWidth-r.Width)/2 || transform.OffsetY != (bwHeight-r.Height)/2 {
		return NavigationMask{}, fmt.Errorf("invalid_navigation_dimensions")
	}
	walkCells := bwWidth * 4 * bwHeight * 4
	m := NavigationMask{Width: bwWidth, Height: bwHeight, Bits: make([]byte, (walkCells+7)/8)}
	if trace {
		m.Causes = make(map[int][]string)
	}
	for i := range m.Bits {
		m.Bits[i] = 0xff
	}
	flat := Terrain{Height: 0, Walkable: true}
	cells := make([]Terrain, r.Width*r.Height)
	present := make([]bool, len(cells))
	if len(r.Terrain) == 0 {
		for i := range cells {
			cells[i], present[i] = flat, true
		}
	} else {
		for _, cell := range r.Terrain {
			index := cell.Y*r.Width + cell.X
			cells[index], present[index] = cell, true
		}
	}
	for y := 0; y < r.Height; y++ {
		for x := 0; x < r.Width; x++ {
			i := y*r.Width + x
			if !present[i] || !cells[i].Walkable || cells[i].Water > 0 {
				continue
			}
			if err := cells[i].ValidateGeometry(); err != nil {
				return NavigationMask{}, fmt.Errorf("unsupported_terrain at %d,%d: %w", x, y, err)
			}
			m.fillTile(x+transform.OffsetX, y+transform.OffsetY, false)
		}
	}
	for y := 0; y < r.Height; y++ {
		for x := 0; x < r.Width; x++ {
			i := y*r.Width + x
			if !present[i] {
				continue
			}
			if x+1 < r.Width && present[i+1] {
				connected, err := TerrainEdgeConnected(cells[i], cells[i+1], 1, 0)
				if err != nil {
					return NavigationMask{}, err
				}
				if !connected {
					m.blockEastEdge(x+transform.OffsetX, y+transform.OffsetY)
				}
			}
			if y+1 < r.Height && present[i+r.Width] {
				connected, err := TerrainEdgeConnected(cells[i], cells[i+r.Width], 0, 1)
				if err != nil {
					return NavigationMask{}, err
				}
				if !connected {
					m.blockSouthEdge(x+transform.OffsetX, y+transform.OffsetY)
				}
			}
		}
	}
	if err := m.blockRaisedPaths(cells, r.Width, r.Height, transform); err != nil {
		return NavigationMask{}, fmt.Errorf("path geometry: %w", err)
	}
	for _, id := range r.IDs() {
		if r.Destroyed[id] {
			continue
		}
		entity := r.Entities[id]
		if !entity.Collision.Blocks {
			continue
		}
		switch entity.Collision.Mode {
		case "", "legacy":
			for _, rect := range transform.Entity(entity).Geometry.Rects {
				m.blockRect(rect, id+":legacy")
			}
		case "height_aware", "conservative":
			if entity.Collision.Mode == "conservative" && len(entity.Collision.Volumes) == 0 {
				for _, rect := range transform.Entity(entity).Geometry.Rects {
					m.blockRect(rect, id+":conservative")
				}
			}
			for _, volume := range entity.Collision.Volumes {
				if err := m.blockVolume(volume, cells, r.Width, r.Height, transform,
					id+"/"+volume.Source); err != nil {
					return NavigationMask{}, fmt.Errorf("collision %s: %w", id, err)
				}
			}
		}
	}
	hash := fnv.New64a()
	_, _ = hash.Write(m.Bits)
	m.Hash = fmt.Sprintf("%016x", hash.Sum64())
	m.DerivationTime = time.Since(started)
	return m, nil
}
