package main

import (
	"crypto/rand"
	"math/big"

	"starcoaster/internal/world"
)

// The mask is the confirmed mask sent to OpenBW. This breadth-first pass is a
// coarse connectivity filter; native placement and hasPath remain authoritative.
func (s *service) perimeterCandidates() []perimeterCandidate {
	w, h := s.scenario.ParkSize[0], s.scenario.ParkSize[1]
	if w < 8 || h < 8 || s.navigationMask.Width == 0 || !s.nativeOccupancyComplete {
		return nil
	}
	index := func(x, y int) int { return y*w + x }
	inside := func(x, y int) bool { return x >= 2 && y >= 2 && x < w-2 && y < h-2 }
	passable := make([]bool, w*h)
	for y := 2; y < h-2; y++ {
		for x := 2; x < w-2; x++ {
			passable[index(x, y)] = !s.navigationMask.BlockedPixel(s.transform.X(x*32+16), s.transform.Y(y*32+16))
		}
	}
	interior := min(12, min(w, h)/3)
	destinations := make([][2]int, w*h)
	reachable := make([]bool, w*h)
	queue := make([][2]int, 0, w*h)
	for y := interior; y < h-interior; y++ {
		for x := interior; x < w-interior; x++ {
			if inside(x, y) && passable[index(x, y)] {
				reachable[index(x, y)] = true
				destinations[index(x, y)] = [2]int{x, y}
				queue = append(queue, [2]int{x, y})
			}
		}
	}
	directions := [][2]int{{1, 0}, {-1, 0}, {0, 1}, {0, -1}}
	for head := 0; head < len(queue); head++ {
		p := queue[head]
		for _, d := range directions {
			x, y := p[0]+d[0], p[1]+d[1]
			if !inside(x, y) || !passable[index(x, y)] || reachable[index(x, y)] {
				continue
			}
			reachable[index(x, y)] = true
			destinations[index(x, y)] = destinations[index(p[0], p[1])]
			queue = append(queue, [2]int{x, y})
		}
	}
	clear := make([]bool, w*h)
	for y := 2; y < h-2; y++ {
		for x := 2; x < w-2; x++ {
			if !passable[index(x, y)] || (x >= 8 && y >= 8 && x < w-8 && y < h-8) {
				continue
			}
			_, clear[index(x, y)] = s.scenarioZoneCandidate(world.SpawnZone{Tiles: [][2]int{{x, y}}}, nil)
		}
	}
	large := false
	for _, group := range s.scenario.ParkDefense.GroupsForWave(s.runtime.NextWaveSequence) {
		if group.UnitType == "zerg_ultralisk" {
			large = true
		}
	}
	candidates := make([]perimeterCandidate, 0)
	for y := 2; y < h-2; y++ {
		for x := 2; x < w-2; x++ {
			if !clear[index(x, y)] || !reachable[index(x, y)] {
				continue
			}
			zone := world.SpawnZone{}
			for dy := -2; dy <= 2; dy++ {
				for dx := -2; dx <= 2; dx++ {
					tx, ty := x+dx, y+dy
					if !inside(tx, ty) || !clear[index(tx, ty)] || !reachable[index(tx, ty)] {
						continue
					}
					if large && (!inside(tx+1, ty) || !inside(tx, ty+1) || !inside(tx+1, ty+1) ||
						!passable[index(tx+1, ty)] || !passable[index(tx, ty+1)] || !passable[index(tx+1, ty+1)]) {
						continue
					}
					zone.Tiles = append(zone.Tiles, [2]int{tx, ty})
				}
			}
			if len(zone.Tiles) >= 4 {
				candidates = append(candidates, perimeterCandidate{
					anchor: [2]int{x, y}, zone: zone, destination: destinations[index(x, y)]})
			}
		}
	}
	return candidates
}

type perimeterCandidate struct {
	anchor      [2]int
	zone        world.SpawnZone
	destination [2]int
}

func (s *service) triggerAutomaticPerimeter() {
	r := s.runtime
	if !s.ready || s.bw == nil || s.controller == nil || !s.nativeOccupancyComplete ||
		s.parkPatch != nil || s.targetPatch != nil || !r.DefenseEnabled ||
		r.NextAutomaticFrame == 0 || r.LastFrame < r.NextAutomaticFrame ||
		r.LastFrame < s.perimeterRetryFrame {
		return
	}
	for _, wave := range r.Waves {
		if wave.Origin == "periodic" && (wave.State == "triggered" || wave.State == "spawning") {
			return
		}
	}
	candidates := s.perimeterCandidates()
	if len(candidates) == 0 {
		s.perimeterRetryFrame = r.LastFrame + 240
		return // no intent or missed-wave backlog while no route exists
	}
	index := 0
	if s.defenseRandomIndex != nil {
		index = s.defenseRandomIndex(len(candidates))
	} else if choice, err := rand.Int(rand.Reader, big.NewInt(int64(len(candidates)))); err == nil {
		index = int(choice.Int64())
	}
	if index < 0 || index >= len(candidates) {
		index = 0
	}
	selected := candidates[index]
	r.CommitAutomaticWave(s.scenario, selected.anchor, selected.zone, selected.destination, s.registry.Revision)
}
