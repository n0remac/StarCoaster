package world

// Transform preserves source identities while expressing geometry in the
// reusable OpenBW map's coordinate space. It never mutates the park registry.
type Transform struct {
	Numerator   int
	Denominator int
	OffsetX     int // StarCraft build tiles, after scaling
	OffsetY     int
}

func Fit(parkWidth, parkHeight, bwWidth, bwHeight int) Transform {
	if parkWidth < 1 || parkHeight < 1 || bwWidth < 1 || bwHeight < 1 {
		return Transform{Numerator: 1, Denominator: 1}
	}
	if bwWidth >= parkWidth && bwHeight >= parkHeight {
		return Transform{Numerator: 1, Denominator: 1,
			OffsetX: (bwWidth - parkWidth) / 2, OffsetY: (bwHeight - parkHeight) / 2}
	}
	if bwWidth*parkHeight <= bwHeight*parkWidth {
		return Transform{Numerator: bwWidth, Denominator: parkWidth}
	}
	return Transform{Numerator: bwHeight, Denominator: parkHeight}
}
func (t Transform) Pixel(value int) int        { return value * t.Numerator / t.Denominator }
func (t Transform) Tile(value int) int         { return value * t.Numerator / t.Denominator }
func (t Transform) InversePixel(value int) int { return value * t.Denominator / t.Numerator }
func (t Transform) X(value int) int            { return t.Pixel(value) + t.OffsetX*32 }
func (t Transform) Y(value int) int            { return t.Pixel(value) + t.OffsetY*32 }
func (t Transform) TileX(value int) int        { return t.Tile(value) + t.OffsetX }
func (t Transform) TileY(value int) int        { return t.Tile(value) + t.OffsetY }
func (t Transform) InverseX(value int) int     { return t.InversePixel(value - t.OffsetX*32) }
func (t Transform) InverseY(value int) int     { return t.InversePixel(value - t.OffsetY*32) }
func (t Transform) Entity(e Entity) Entity {
	e = cloneEntity(e)
	e.Position.X = t.X(e.Position.X)
	e.Position.Y = t.Y(e.Position.Y)
	for i := range e.Geometry.Cells {
		e.Geometry.Cells[i].X = t.TileX(e.Geometry.Cells[i].X)
		e.Geometry.Cells[i].Y = t.TileY(e.Geometry.Cells[i].Y)
	}
	for i := range e.Geometry.Rects {
		r := &e.Geometry.Rects[i]
		endX, endY := t.X(r.X+r.Width), t.Y(r.Y+r.Height)
		r.X = t.X(r.X)
		r.Y = t.Y(r.Y)
		r.Width = endX - r.X
		r.Height = endY - r.Y
		if r.Width < 1 {
			r.Width = 1
		}
		if r.Height < 1 {
			r.Height = 1
		}
	}
	return e
}
func (t Transform) Terrain(cells []Terrain) []Terrain {
	result := make([]Terrain, 0, len(cells))
	positions := make(map[Point]int, len(cells))
	for _, cell := range cells {
		cell.X = t.TileX(cell.X)
		cell.Y = t.TileY(cell.Y)
		p := Point{cell.X, cell.Y}
		if index, ok := positions[p]; ok {
			result[index] = cell
		} else {
			positions[p] = len(result)
			result = append(result, cell)
		}
	}
	return result
}
