package main

import (
	"path/filepath"
	"testing"

	"starcoaster/internal/world"
)

func TestGatherRequiresCurrentNativeResourceGeneration(t *testing.T) {
	scenario, err := world.LoadScenario(filepath.Join("..", "..", "scenarios", "economy-e1", "scenario.json"))
	if err != nil {
		t.Fatal(err)
	}
	resources := world.NewResourceLedger(scenario, "session-a")
	for _, observation := range []world.ResourceObservation{
		{SiteID: "mineral-a", Generation: 1, NativeID: "4", Type: "mineral_field", Owner: 11,
			X: (28+96)*32 + 32, Y: (9+96)*32 + 16, Amount: 1500, Lifecycle: "deposit"},
		{SiteID: "geyser", Generation: 1, NativeID: "10", Type: "vespene_geyser", Owner: 11,
			X: (34+96)*32 + 64, Y: (8+96)*32 + 32, Amount: 5000, Lifecycle: "deposit"},
	} {
		resources.Observe("publisher", observation)
		resources.Observe("controller", observation)
	}
	s := &service{scenario: scenario, actors: world.NewActorRegistry("session-a"), resources: resources}
	command := worldCommand{UnitIDs: []string{"openbw:2506"}, TargetID: "mineral-a", TargetGeneration: 1}
	if err := s.prepareGatherCommand(&command); err != nil {
		t.Fatal(err)
	}
	if command.TargetNativeID != "4" || command.NativeGeneration != 1 {
		t.Fatalf("wrong native target: %+v", command)
	}
	command.TargetGeneration = 2
	if err := s.prepareGatherCommand(&command); err == nil {
		t.Fatal("stale mineral generation accepted")
	}
	command.TargetGeneration = 1
	command.TargetID = "geyser"
	if err := s.prepareGatherCommand(&command); err == nil {
		t.Fatal("bare geyser accepted for gathering")
	}
	command.TargetID = "mineral-a"
	command.UnitIDs = []string{"scenario:worker-a"}
	if err := s.prepareGatherCommand(&command); err == nil {
		t.Fatal("non-native worker accepted")
	}
}
