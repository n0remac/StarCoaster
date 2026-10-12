package world

// Transform preserves source identities while expressing geometry in the
// reusable OpenBW map's coordinate space. It never mutates the park registry.
type Transform struct {
	Numerator   int
	Denominator int
}

func Fit(parkWidth, parkHeight, bwWidth, bwHeight int) Transform {
	if parkWidth < 1 || parkHeight < 1 || bwWidth < 1 || bwHeight < 1 {
		return Transform{1, 1}
	}
	if bwWidth >= parkWidth && bwHeight >= parkHeight {
		return Transform{1, 1}
	}
	if bwWidth*parkHeight <= bwHeight*parkWidth {
		return Transform{bwWidth, parkWidth}
	}
	return Transform{bwHeight, parkHeight}
}
func (t Transform) Pixel(value int) int        { return value * t.Numerator / t.Denominator }
func (t Transform) Tile(value int) int         { return value * t.Numerator / t.Denominator }
func (t Transform) InversePixel(value int) int { return value * t.Denominator / t.Numerator }
func (t Transform) Entity(e Entity) Entity {
	e = cloneEntity(e)
	e.Position.X = t.Pixel(e.Position.X)
	e.Position.Y = t.Pixel(e.Position.Y)
	for i := range e.Geometry.Cells {
		e.Geometry.Cells[i].X = t.Tile(e.Geometry.Cells[i].X)
		e.Geometry.Cells[i].Y = t.Tile(e.Geometry.Cells[i].Y)
	}
	for i := range e.Geometry.Rects {
		r := &e.Geometry.Rects[i]
		endX, endY := t.Pixel(r.X+r.Width), t.Pixel(r.Y+r.Height)
		r.X = t.Pixel(r.X)
		r.Y = t.Pixel(r.Y)
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
		cell.X = t.Tile(cell.X)
		cell.Y = t.Tile(cell.Y)
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
