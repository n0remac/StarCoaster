package main

import (
	"encoding/json"
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
	return s
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
	if len(s.runtime.Waves) != 1 || s.runtime.NextAutomaticFrame != 6100 {
		t.Fatal("recovery did not resume one interval")
	}
}
