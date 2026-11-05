package main

import (
	"crypto/rand"
	"fmt"
	"log"
	"math/big"
	"time"

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

type perimeterQueryState struct {
	peer         *peer
	revision     uint64
	replaceIndex int // -1 creates a new wave; otherwise replaces an unsubmitted selection
	sequence     int
	candidates   []perimeterCandidate
	selected     perimeterCandidate
	queryID      string
	tries        int
	sentFrame    int
}

func (s *service) triggerAutomaticPerimeter() {
	r := s.runtime
	if s.pendingPerimeter != nil {
		if s.pendingPerimeter.peer != s.bw || s.pendingPerimeter.revision != s.registry.Revision ||
			r.LastFrame-s.pendingPerimeter.sentFrame >= 120 {
			s.pendingPerimeter = nil
			s.perimeterRetryFrame = r.LastFrame + 240
		}
		return
	}
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
	s.startPerimeterQuery(-1)
}

func (s *service) choosePerimeterIndex(count int) int {
	index := 0
	if s.defenseRandomIndex != nil {
		index = s.defenseRandomIndex(count)
	} else if choice, err := rand.Int(rand.Reader, big.NewInt(int64(count))); err == nil {
		index = int(choice.Int64())
	}
	if index < 0 || index >= count {
		index = 0
	}
	return index
}

func (s *service) startPerimeterQuery(replaceIndex int) {
	started := time.Now()
	candidates := s.perimeterCandidates()
	log.Printf("automatic perimeter candidates=%d elapsed_us=%d size=%dx%d revision=%d",
		len(candidates), time.Since(started).Microseconds(), s.scenario.ParkSize[0],
		s.scenario.ParkSize[1], s.registry.Revision)
	if len(candidates) == 0 {
		s.perimeterRetryFrame = s.runtime.LastFrame + 240
		if replaceIndex >= 0 {
			s.runtime.Waves[replaceIndex].FailureReason = "Waves waiting: no reachable edge location"
		}
		return
	}
	sequence := s.runtime.NextWaveSequence
	if replaceIndex >= 0 {
		sequence = s.runtime.Waves[replaceIndex].Sequence
	}
	s.pendingPerimeter = &perimeterQueryState{peer: s.bw, revision: s.registry.Revision,
		replaceIndex: replaceIndex, sequence: sequence, candidates: candidates}
	s.sendNextPerimeterQuery()
}

func (s *service) sendNextPerimeterQuery() {
	state := s.pendingPerimeter
	if state == nil {
		return
	}
	if state.tries >= 64 || len(state.candidates) == 0 {
		if state.replaceIndex >= 0 {
			s.runtime.Waves[state.replaceIndex].FailureReason = "Waves waiting: no reachable edge location"
		}
		s.pendingPerimeter = nil
		s.perimeterRetryFrame = s.runtime.LastFrame + 240
		return
	}
	index := s.choosePerimeterIndex(len(state.candidates))
	state.selected = state.candidates[index]
	state.candidates[index] = state.candidates[len(state.candidates)-1]
	state.candidates = state.candidates[:len(state.candidates)-1]
	state.tries++
	state.sentFrame = s.runtime.LastFrame
	state.queryID = fmt.Sprintf("perimeter:%s:%d:%d:%d", s.registry.Session, state.sequence, state.revision, state.tries)
	tiles := make([][2]int, 0, len(state.selected.zone.Tiles))
	for _, tile := range state.selected.zone.Tiles {
		tiles = append(tiles, [2]int{s.transform.X(tile[0]*32 + 16), s.transform.Y(tile[1]*32 + 16)})
	}
	types := []string{}
	for _, group := range s.scenario.ParkDefense.GroupsForWave(state.sequence) {
		types = append(types, group.UnitType)
	}
	destination := state.selected.destination
	payload := map[string]any{"query_id": state.queryID, "tiles": tiles,
		"destination": [2]int{s.transform.X(destination[0]*32 + 16), s.transform.Y(destination[1]*32 + 16)},
		"unit_types":  types}
	if err := s.bw.send(world.Message("scenario.perimeter.query", s.registry.Session, state.queryID, "bridge", state.revision, payload)); err != nil {
		s.pendingPerimeter = nil
		s.perimeterRetryFrame = s.runtime.LastFrame + 240
	}
}

func (s *service) acceptPerimeterRoute(queryID string, accepted bool, indices []int) {
	state := s.pendingPerimeter
	if state == nil || queryID != state.queryID || state.revision != s.registry.Revision || state.peer != s.bw {
		return
	}
	zone := world.SpawnZone{}
	seen := map[int]bool{}
	anchorValid := false
	if accepted {
		for _, index := range indices {
			if index < 0 || index >= len(state.selected.zone.Tiles) || seen[index] {
				continue
			}
			seen[index] = true
			tile := state.selected.zone.Tiles[index]
			zone.Tiles = append(zone.Tiles, tile)
			if tile == state.selected.anchor { anchorValid = true }
		}
	}
	if len(zone.Tiles) < 4 || !anchorValid {
		s.sendNextPerimeterQuery()
		return
	}
	selected := state.selected
	if state.replaceIndex < 0 {
		if !s.runtime.CommitAutomaticWave(s.scenario, selected.anchor, zone, selected.destination, state.revision) {
			s.pendingPerimeter = nil
			return
		}
	} else {
		wave := &s.runtime.Waves[state.replaceIndex]
		if wave.Submitted != 0 || wave.State != "triggered" {
			s.pendingPerimeter = nil
			return
		}
		wave.SpawnAnchor, wave.Destination = &selected.anchor, &selected.destination
		wave.FixedZone = zone
		wave.SelectionRevision = state.revision
		wave.FailureReason = ""
	}
	s.pendingPerimeter = nil
	s.perimeterRetryFrame = 0
	if !s.saveScenarioRuntime() {
		s.scenarioRuntimeError(fmt.Errorf("scenario_journal_unavailable"))
		return
	}
	s.publishScenarioStatus(false)
}

// A confirmed construction revision can invalidate a selected edge before
// the first native submission. Once any unit is submitted, the wave remains in
// its recorded cluster and reports a local shortfall instead of changing side.
func (s *service) refreshUnsubmittedAutomaticWaves() {
	if !s.ready || s.pendingPerimeter != nil || !s.nativeOccupancyComplete || s.parkPatch != nil || s.targetPatch != nil ||
		s.runtime.LastFrame < s.perimeterRetryFrame {
		return
	}
	for i := range s.runtime.Waves {
		wave := &s.runtime.Waves[i]
		if wave.State != "triggered" || wave.Submitted != 0 ||
			wave.SelectionRevision == s.registry.Revision {
			continue
		}
		s.startPerimeterQuery(i)
		return
	}
}
