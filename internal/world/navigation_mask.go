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
	DerivationTime time.Duration `json:"-"`
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
			m.set(x*4+column, y*4+row, true)
		}
	}
}

func (m NavigationMask) blockSouthEdge(x, y int) {
	for row := 0; row < 8; row++ {
		for column := 0; column < 4; column++ {
			m.set(x*4+column, y*4+row, true)
		}
	}
}

func (m NavigationMask) blockRect(r Rect) {
	for y := r.Y / 8; y <= (r.Y+r.Height-1)/8; y++ {
		for x := r.X / 8; x <= (r.X+r.Width-1)/8; x++ {
			m.set(x, y, true)
		}
	}
}

// DeriveNavigation is the only world-to-native collision derivation. Missing
// cells in a partial export are blocked; an empty legacy export means flat
// ground inside the park. Padding outside the centered park stays blocked.
func DeriveNavigation(r *Registry, transform Transform, bwWidth, bwHeight int) (NavigationMask, error) {
	started := time.Now()
	if r == nil || r.Width < 1 || r.Height < 1 || bwWidth < r.Width || bwHeight < r.Height ||
		bwWidth > 256 || bwHeight > 256 || transform.Numerator != 1 || transform.Denominator != 1 ||
		transform.OffsetX != (bwWidth-r.Width)/2 || transform.OffsetY != (bwHeight-r.Height)/2 {
		return NavigationMask{}, fmt.Errorf("invalid_navigation_dimensions")
	}
	walkCells := bwWidth * 4 * bwHeight * 4
	m := NavigationMask{Width: bwWidth, Height: bwHeight, Bits: make([]byte, (walkCells+7)/8)}
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
	for _, id := range r.IDs() {
		if r.Destroyed[id] {
			continue
		}
		entity := r.Entities[id]
		if !entity.Collision.Blocks {
			continue
		}
		for _, rect := range transform.Entity(entity).Geometry.Rects {
			m.blockRect(rect)
		}
	}
	hash := fnv.New64a()
	_, _ = hash.Write(m.Bits)
	m.Hash = fmt.Sprintf("%016x", hash.Sum64())
	m.DerivationTime = time.Since(started)
	return m, nil
}
