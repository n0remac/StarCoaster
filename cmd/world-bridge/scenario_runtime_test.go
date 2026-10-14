package main

import (
	"strings"
	"testing"

	"starcoaster/internal/world"
)

func TestBridgeScenarioJournalPreventsInterWaveVictoryAndDuplicateIssue(t *testing.T) {
	s, _ := spawnService(t)
	frames := 10
	scenario := &world.Scenario{Version: 2, ID: "scenario-test", ParkSize: [2]int{64, 64},
		SpawnZones: map[string]world.SpawnZone{"east": {Tiles: [][2]int{{43, 56}, {44, 56}, {45, 56}}}},
		Waves: []world.ScenarioWave{
			{ID: "first", Trigger: world.WaveTrigger{Type: "on_ready"}, Groups: []world.WaveGroup{{UnitType: "zerg_zergling", Count: 1, SpawnZone: "east"}}},
			{ID: "timed", Trigger: world.WaveTrigger{Type: "elapsed_frames", Frames: &frames}, Groups: []world.WaveGroup{{UnitType: "zerg_zergling", Count: 1, SpawnZone: "east"}}},
			{ID: "dependent", Trigger: world.WaveTrigger{Type: "wave_cleared", WaveID: "timed"}, Groups: []world.WaveGroup{{UnitType: "zerg_zergling", Count: 1, SpawnZone: "east"}}},
		}}
	s.scenario = scenario
	s.objectiveID = "carousel"
	s.nativeOccupancyComplete = true
	s.navigationMask = world.NavigationMask{Width: 128, Height: 128, Bits: make([]byte, 128*4*128*4/8)}
	s.bw = nil // inspect queued intent before any native issue
	if err := s.initScenarioRuntime(); err != nil {
		t.Fatal(err)
	}
	s.advanceScenarioRuntime(100, 1, nil)
	if len(s.spawns.Order) != 1 || s.runtime.Waves[0].State != "spawning" {
		t.Fatalf("first wave not submitted: %+v", s.runtime.Waves)
	}
	firstID := s.spawns.Order[0]
	s.lastMarines, s.lastZerglings = 6, 0
	s.announceOutcome(6, 0)
	if s.outcome != "" {
		t.Fatal("victory between waves")
	}
	s.advanceScenarioRuntime(105, 2, nil)
	if len(s.spawns.Order) != 1 {
		t.Fatal("timed wave fired early")
	}
	// A Go-only bridge restart reloads the same intent and queue. A second
	// readiness/snapshot cannot submit the first wave again.
	restarted, _ := spawnService(t)
	restarted.spawnJournalPath = s.spawnJournalPath
	restarted.spawns = nil
	restarted.initSpawns("session-a")
	restarted.scenario = scenario
	restarted.bw = nil
	restarted.nativeOccupancyComplete = true
	restarted.navigationMask = s.navigationMask
	if err := restarted.initScenarioRuntime(); err != nil {
		t.Fatal(err)
	}
	restarted.advanceScenarioRuntime(106, 3, nil)
	if len(restarted.spawns.Order) != 1 || restarted.spawns.Order[0] != firstID {
		t.Fatal("restart duplicated first wave")
	}
	restarted.advanceScenarioRuntime(110, 4, nil)
	if len(restarted.spawns.Order) != 2 || restarted.runtime.Waves[1].State != "spawning" {
		t.Fatal("elapsed frame wave did not fire")
	}
	restarted.announceOutcome(6, 0)
	if restarted.outcome != "" {
		t.Fatal("victory before dependent wave")
	}
}

func TestBridgeTerminalDemolitionSurvivesJournalRecovery(t *testing.T) {
	s, _ := spawnService(t)
	scenario := &world.Scenario{Version: 2, ID: "named-defense", DisplayName: "Named Defense", ParkSize: [2]int{64, 64},
		Objectives: []world.ScenarioObjective{{ID: "defend-carousel", Description: "Defend the carousel", EntityKind: "ride", EntityType: "rct2.ride.mgr1", EntityName: "Frontier Carousel", Required: true}},
		Waves:      []world.ScenarioWave{{ID: "first"}}}
	scenario.InitialAI.Objective = "defend-carousel"
	scenario.Defeat.ObjectiveDestroyed = "defend-carousel"
	scenario.StartingUnits.Marines = make([][2]int, 6)
	scenario.StartingUnits.Zerglings = make([][2]int, 12)
	s.scenario = scenario
	s.objectiveID = "openrct2:ride:100#1"
	if err := s.initScenarioRuntime(); err != nil {
		t.Fatal(err)
	}
	s.runtime.ObjectiveEntityID = s.objectiveID
	s.runtime.ObjectiveDestroyed = true
	s.registry.Destroyed[s.objectiveID] = true
	s.announceOutcome(6, 0)
	if s.outcome != "defeat" || !s.saveScenarioRuntime() {
		t.Fatal("confirmed demolition not durable")
	}
	recovered := &service{registry: world.NewRegistry(), scenario: scenario, spawnJournalPath: s.spawnJournalPath}
	if err := recovered.registry.Replace("session-a", 2, 64, 64, nil, nil); err != nil {
		t.Fatal(err)
	}
	if err := recovered.initScenarioRuntime(); err != nil {
		t.Fatal(err)
	}
	if recovered.runtime.Outcome != "defeat" || !recovered.runtime.ObjectiveDestroyed {
		t.Fatal("terminal outcome was lost")
	}
	ready := world.Ready{Navigation: "native", Resuming: true, Marines: 6, Zerglings: 0}
	if err := scenario.CheckReadyWithRuntimeState(recovered.registry, nil, ready, 0, 0, true); err != nil {
		t.Fatalf("destroyed objective was required to reappear: %v", err)
	}
	status := recovered.currentScenarioStatus()
	if status.Outcome != "" {
		t.Fatal("status must be loaded into service on readiness")
	}
	recovered.outcome = recovered.runtime.Outcome
	status = recovered.currentScenarioStatus()
	if status.Outcome != "defeat" || !strings.Contains(status.Objective, "carousel") {
		t.Fatalf("terminal status lost: %+v", status)
	}
}
