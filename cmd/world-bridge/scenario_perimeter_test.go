package main

import (
	"encoding/json"
	"io"
	"net"
	"testing"

	"starcoaster/internal/world"
)

func automaticDefenseService(t *testing.T) *service {
	t.Helper()
	s := defenseService(t)
	s.scenario.ParkDefense.ManualActivation = false
	s.scenario.ParkDefense.FixedSpawn = false
	s.scenario.ParkDefense.SpawnPolicy = "automatic_perimeter"
	s.runtime = world.NewScenarioRuntime(s.scenario, s.registry.Session)
	if err := s.runtime.AcceptFrame(100, 1, true); err != nil {
		t.Fatal(err)
	}
	s.runtime.Trigger(s.scenario)
	bridge, native := net.Pipe()
	s.bw = &peer{Conn: bridge}
	go io.Copy(io.Discard, native)
	t.Cleanup(func() { bridge.Close(); native.Close() })
	return s
}

func acceptCurrentPerimeter(t *testing.T, s *service) {
	t.Helper()
	if s.pendingPerimeter == nil {
		t.Fatal("missing native route query")
	}
	indices := make([]int, len(s.pendingPerimeter.selected.zone.Tiles))
	for i := range indices {
		indices[i] = i
	}
	s.acceptPerimeterRoute(s.pendingPerimeter.queryID, true, indices)
}

func TestAutomaticPerimeterCandidatesAndDurableChoice(t *testing.T) {
	s := automaticDefenseService(t)
	candidates := s.perimeterCandidates()
	sides := [4]bool{}
	for _, candidate := range candidates {
		x, y := candidate.anchor[0], candidate.anchor[1]
		if x < 8 {
			sides[0] = true
		}
		if x >= 56 {
			sides[1] = true
		}
		if y < 8 {
			sides[2] = true
		}
		if y >= 56 {
			sides[3] = true
		}
		if len(candidate.zone.Tiles) < 4 {
			t.Fatal("non-cluster candidate")
		}
	}
	for i, ok := range sides {
		if !ok {
			t.Fatalf("side %d has no candidate", i)
		}
	}
	s.defenseRandomIndex = func(n int) int { return n - 1 }
	s.runtime.LastFrame = 2980
	s.triggerAutomaticPerimeter()
	acceptCurrentPerimeter(t, s)
	if len(s.runtime.Waves) != 1 || s.runtime.Waves[0].SpawnAnchor == nil ||
		*s.runtime.Waves[0].SpawnAnchor != candidates[len(candidates)-1].anchor {
		t.Fatalf("selection not committed: %+v", s.runtime.Waves)
	}
	encoded, _ := json.Marshal(s.runtime)
	var recovered world.ScenarioRuntime
	if err := json.Unmarshal(encoded, &recovered); err != nil {
		t.Fatal(err)
	}
	if err := recovered.Validate(s.scenario, s.registry.Session); err != nil {
		t.Fatal(err)
	}
	if *recovered.Waves[0].SpawnAnchor != candidates[len(candidates)-1].anchor {
		t.Fatal("recovery moved wave")
	}
	s.triggerAutomaticPerimeter()
	if len(s.runtime.Waves) != 1 {
		t.Fatal("duplicate readiness created another wave")
	}
}

func TestAutomaticPerimeterSeededChoiceCanReachEverySide(t *testing.T) {
	for side := 0; side < 4; side++ {
		s := automaticDefenseService(t)
		candidates := s.perimeterCandidates()
		choice := -1
		for index, candidate := range candidates {
			x, y := candidate.anchor[0], candidate.anchor[1]
			if (side == 0 && x < 8) || (side == 1 && x >= 56) ||
				(side == 2 && y < 8) || (side == 3 && y >= 56) {
				choice = index
				break
			}
		}
		if choice < 0 {
			t.Fatalf("side %d has no reachable candidate", side)
		}
		s.defenseRandomIndex = func(n int) int { return choice }
		s.runtime.LastFrame = 2980
		s.triggerAutomaticPerimeter()
		acceptCurrentPerimeter(t, s)
		if len(s.runtime.Waves) != 1 || s.runtime.Waves[0].SpawnAnchor == nil ||
			*s.runtime.Waves[0].SpawnAnchor != candidates[choice].anchor {
			t.Fatalf("side %d did not commit seeded location: %+v", side, s.runtime.Waves)
		}
	}
}

func TestAutomaticPerimeterWaitsWithoutRouteOrBacklog(t *testing.T) {
	s := automaticDefenseService(t)
	for i := range s.navigationMask.Bits {
		s.navigationMask.Bits[i] = 0xff
	}
	s.runtime.LastFrame = 2980
	s.triggerAutomaticPerimeter()
	if len(s.runtime.Waves) != 0 || s.perimeterRetryFrame != 3220 {
		t.Fatal("blocked route committed an attack")
	}
	s.runtime.LastFrame = 3100
	s.triggerAutomaticPerimeter()
	if len(s.runtime.Waves) != 0 {
		t.Fatal("waiting route caught up")
	}
	for i := range s.navigationMask.Bits {
		s.navigationMask.Bits[i] = 0
	}
	s.runtime.LastFrame = 3220
	s.triggerAutomaticPerimeter()
	acceptCurrentPerimeter(t, s)
	if len(s.runtime.Waves) != 1 || s.runtime.NextAutomaticFrame != 6100 {
		t.Fatal("recovery did not resume one interval")
	}
}

func TestAutomaticPerimeterPauseAndReadinessLossDoNotBacklog(t *testing.T) {
	s := automaticDefenseService(t)
	s.ready = false
	s.runtime.LastFrame = 2980
	s.triggerAutomaticPerimeter()
	if s.pendingPerimeter != nil || len(s.runtime.Waves) != 0 || s.runtime.NextAutomaticFrame != 2980 {
		t.Fatal("unready native participants created a wave")
	}
	s.ready = true
	s.triggerAutomaticPerimeter()
	acceptCurrentPerimeter(t, s)
	if len(s.runtime.Waves) != 1 || s.runtime.NextAutomaticFrame != 5860 {
		t.Fatal("readiness recovery did not commit one wave")
	}
	s.triggerAutomaticPerimeter() // paused simulation: native frame did not advance
	if len(s.runtime.Waves) != 1 {
		t.Fatal("paused frame duplicated a wave")
	}
	s.runtime.Waves[0].State = "cleared"
	s.ready = false
	s.runtime.LastFrame = 9000
	s.triggerAutomaticPerimeter()
	if s.pendingPerimeter != nil || len(s.runtime.Waves) != 1 || s.runtime.NextAutomaticFrame != 5860 {
		t.Fatal("readiness loss accumulated due waves")
	}
	s.ready = true
	s.triggerAutomaticPerimeter()
	acceptCurrentPerimeter(t, s)
	if len(s.runtime.Waves) != 2 || s.runtime.NextAutomaticFrame != 11880 {
		t.Fatal("readiness recovery caught up missed intervals")
	}
}

func TestAutomaticPerimeterReselectsOnlyBeforeNativeSubmission(t *testing.T) {
	s := automaticDefenseService(t)
	s.defenseRandomIndex = func(int) int { return 0 }
	s.runtime.LastFrame = 2980
	s.triggerAutomaticPerimeter()
	acceptCurrentPerimeter(t, s)
	first := *s.runtime.Waves[0].SpawnAnchor
	s.registry.Revision++ // confirmed construction changes the navigation generation
	s.defenseRandomIndex = func(n int) int { return n - 1 }
	s.refreshUnsubmittedAutomaticWaves()
	acceptCurrentPerimeter(t, s)
	wave := &s.runtime.Waves[0]
	if *wave.SpawnAnchor == first || wave.SelectionRevision != s.registry.Revision {
		t.Fatalf("unsubmitted origin did not refresh: %+v", wave)
	}
	committed := *wave.SpawnAnchor
	wave.Submitted = 1
	s.registry.Revision++
	s.refreshUnsubmittedAutomaticWaves()
	if *wave.SpawnAnchor != committed {
		t.Fatal("submitted wave changed perimeter origin")
	}
}

func TestAutomaticPerimeterCoversRectangularParkAndBlockedCenter(t *testing.T) {
	s := automaticDefenseService(t)
	s.scenario.ParkSize = [2]int{48, 24}
	// A blocked geometric center must not become the only inward destination.
	centerX, centerY := s.transform.X(24*32+16)/8, s.transform.Y(12*32+16)/8
	for y := centerY - 4; y < centerY+4; y++ {
		for x := centerX - 4; x < centerX+4; x++ {
			index := y*s.navigationMask.Width*4 + x
			s.navigationMask.Bits[index>>3] |= 1 << (index & 7)
		}
	}
	candidates := s.perimeterCandidates()
	if len(candidates) == 0 {
		t.Fatal("blocked center removed every valid edge")
	}
	sides := [4]bool{}
	for _, candidate := range candidates {
		x, y := candidate.anchor[0], candidate.anchor[1]
		if x < 8 {
			sides[0] = true
		}
		if x >= 40 {
			sides[1] = true
		}
		if y < 8 {
			sides[2] = true
		}
		if y >= 16 {
			sides[3] = true
		}
		if candidate.destination == [2]int{24, 12} {
			t.Fatal("blocked center selected as destination")
		}
	}
	for i, ok := range sides {
		if !ok {
			t.Fatalf("rectangular side %d has no candidate", i)
		}
	}
}

func TestAutomaticPerimeterTinyMapWaitsWithoutIntent(t *testing.T) {
	s := automaticDefenseService(t)
	s.scenario.ParkSize = [2]int{7, 7}
	s.runtime.LastFrame = 2980
	s.triggerAutomaticPerimeter()
	if len(s.runtime.Waves) != 0 || s.pendingPerimeter != nil ||
		s.perimeterRetryFrame != 3220 {
		t.Fatal("tiny map created a wave instead of waiting for a valid edge")
	}
}

func TestAutomaticPerimeterWaitsForNativeRouteDecision(t *testing.T) {
	s := automaticDefenseService(t)
	s.runtime.LastFrame = 2980
	s.triggerAutomaticPerimeter()
	if len(s.runtime.Waves) != 0 {
		t.Fatal("wave committed before native route verification")
	}
	if s.pendingPerimeter == nil {
		t.Fatal("native route query was not issued")
	}
	selected := s.pendingPerimeter.selected
	acceptCurrentPerimeter(t,s)
	if len(s.runtime.Waves) != 1 || *s.runtime.Waves[0].SpawnAnchor != selected.anchor {
		t.Fatal("verified route was not committed")
	}
}

func TestAutomaticPerimeterRejectsNativeRoutesWithoutBacklog(t *testing.T) {
	s := automaticDefenseService(t)
	s.defenseRandomIndex = func(int) int { return 0 }
	s.runtime.LastFrame = 2980
	s.triggerAutomaticPerimeter()
	s.acceptPerimeterRoute("stale-query", true, []int{0, 1, 2, 3})
	if len(s.runtime.Waves) != 0 || s.pendingPerimeter == nil {
		t.Fatal("stale result changed selection")
	}
	for i := 0; i < 64; i++ {
		if s.pendingPerimeter == nil {
			t.Fatal("native rejection ended too early")
		}
		s.acceptPerimeterRoute(s.pendingPerimeter.queryID, false, nil)
	}
	if s.pendingPerimeter != nil || len(s.runtime.Waves) != 0 || s.perimeterRetryFrame != 3220 {
		t.Fatal("native failures committed wave or accumulated backlog")
	}
	s.runtime.LastFrame = 3220
	s.triggerAutomaticPerimeter()
	acceptCurrentPerimeter(t, s)
	if len(s.runtime.Waves) != 1 || s.runtime.NextAutomaticFrame != 6100 {
		t.Fatal("native route recovery did not resume one interval")
	}
}
