package main

import (
	"fmt"
	"strings"
	"testing"

	"starcoaster/internal/world"
)

func parkDefenseTestScenario() *world.Scenario {
	return &world.Scenario{Version: 2, ID: "repeat", Mode: "park_defense",
		SpawnZones: map[string]world.SpawnZone{
			"north": {Tiles: [][2]int{{20, 20}, {21, 20}, {22, 20}, {23, 20}, {20, 21}, {21, 21}, {22, 21}, {23, 21}}},
			"south": {Tiles: [][2]int{{20, 40}, {21, 40}, {22, 40}, {23, 40}, {20, 41}, {21, 41}, {22, 41}, {23, 41}}},
		}, ParkDefense: &world.ParkDefenseWaves{InitialDelayFrames: 10000, IntervalFrames: 10000,
			UnitsPerWave: 8, ManualCooldownFrames: 0, SpawnZones: []string{"north", "south"}}}
}

func TestParkDefenseFallbackAndTwentyFourReusableWaves(t *testing.T) {
	s, _ := spawnService(t)
	s.scenario = parkDefenseTestScenario()
	s.nativeOccupancyComplete = true
	s.navigationMask = world.NavigationMask{Width: 128, Height: 128, Bits: make([]byte, 128*4*128*4/8)}
	s.bw = nil // inspect the durable queue without issuing native commands
	if err := s.initScenarioRuntime(); err != nil {
		t.Fatal(err)
	}
	s.advanceScenarioRuntime(100, 1, nil)
	for _, tile := range s.scenario.SpawnZones["north"].Tiles {
		s.nativeOccupants = append(s.nativeOccupants, world.NativeOccupant{
			X: s.transform.X(tile[0]*32 + 16), Y: s.transform.Y(tile[1]*32 + 16)})
	}
	if _, err := s.runtime.RequestManual(s.scenario, "wave-request-1", 2, 1); err != nil {
		t.Fatal(err)
	}
	s.advanceScenarioRuntime(101, 2, nil)
	if len(s.spawns.Order) != 8 {
		t.Fatalf("blocked primary did not fall back to another zone: %d", len(s.spawns.Order))
	}
	for _, id := range s.spawns.Order {
		request, _ := s.spawns.Request(id)
		if request.Y/32 < 40 {
			t.Fatalf("fallback used blocked northern tile: %+v", request)
		}
	}
	// Native actors leave the edge before the next wave. Settled queue entries
	// must not hold their former spawn positions forever.
	s.nativeOccupants = nil
	actorSequence := 3000
	for wave := 1; wave <= 24; wave++ {
		if wave > 1 {
			if _, err := s.runtime.RequestManual(s.scenario, fmt.Sprintf("wave-request-%d", wave), 2, wave); err != nil {
				t.Fatal(err)
			}
			s.advanceScenarioRuntime(100+wave, uint64(1+wave), nil)
		}
		for {
			execute, ok := s.spawns.Next()
			if !ok {
				break
			}
			if err := s.spawns.Issue(execute); err != nil {
				t.Fatal(err)
			}
			actorSequence++
			actor := fmt.Sprintf("openbw:%d", actorSequence)
			if err := s.spawns.Created(execute.RequestID, 0, actor, execute.X, execute.Y); err != nil {
				t.Fatal(err)
			}
			if err := s.spawns.Ready(execute.RequestID, 0, actor); err != nil {
				t.Fatal(err)
			}
		}
		if s.spawns.PendingCount() != 0 || len(s.spawns.Order) != wave*8 {
			t.Fatalf("wave %d did not settle exactly eight actors: pending=%d orders=%d", wave,
				s.spawns.PendingCount(), len(s.spawns.Order))
		}
	}
}

func TestParkDefenseWaitsForNativeActorCapacity(t *testing.T) {
	s, _ := spawnService(t)
	s.scenario = parkDefenseTestScenario()
	s.nativeOccupancyComplete = true
	s.navigationMask = world.NavigationMask{Width: 128, Height: 128, Bits: make([]byte, 128*4*128*4/8)}
	s.bw = nil
	if err := s.initScenarioRuntime(); err != nil {
		t.Fatal(err)
	}
	s.advanceScenarioRuntime(100, 1, nil)
	if _, err := s.runtime.RequestManual(s.scenario, "capacity-wave", 2, 1); err != nil {
		t.Fatal(err)
	}
	s.lastMarines = s.actorLimit()
	s.advanceScenarioRuntime(101, 2, nil)
	if len(s.spawns.Order) != 0 || s.runtime.Waves[0].FailureReason != "spawn_capacity_unavailable" {
		t.Fatal("actor cap was bypassed or its blocked reason was lost")
	}
	s.lastMarines = 5
	s.advanceScenarioRuntime(102, 3, nil)
	if len(s.spawns.Order) != 8 || s.runtime.Waves[0].FailureReason != "" {
		t.Fatal("capacity-blocked wave did not resume")
	}
}

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

func TestManualObjectiveRemovalKeepsDistinctDurableDefeat(t *testing.T) {
	s, _ := spawnService(t)
	scenario := &world.Scenario{Version: 2, ID: "manual-objective", ParkSize: [2]int{64, 64},
		Objectives: []world.ScenarioObjective{{ID: "protect", Required: true}}}
	scenario.InitialAI.Objective = "protect"
	scenario.Defeat.ObjectiveDestroyed = "protect"
	s.scenario = scenario
	s.objectiveID = "openrct2:ride:100#1"
	if err := s.initScenarioRuntime(); err != nil {
		t.Fatal(err)
	}
	s.runtime.ObjectiveEntityID = s.objectiveID
	s.runtime.ObjectiveRemoved = true
	s.announceOutcome(6, 0)
	if s.outcome != "defeat" || s.registry.Destroyed[s.objectiveID] || s.runtime.ObjectiveDestroyed {
		t.Fatal("manual objective removal was confused with combat destruction")
	}
	recovered := &service{registry: world.NewRegistry(), scenario: scenario, spawnJournalPath: s.spawnJournalPath}
	if err := recovered.registry.Replace("session-a", 2, 64, 64, nil, nil); err != nil {
		t.Fatal(err)
	}
	if err := recovered.initScenarioRuntime(); err != nil {
		t.Fatal(err)
	}
	if recovered.runtime.Outcome != "defeat" || !recovered.runtime.ObjectiveRemoved ||
		recovered.runtime.ObjectiveDestroyed {
		t.Fatal("manual objective outcome was not recovered distinctly")
	}
}

func TestBridgeRestoredWaveRequiresReconciliationAndCompleteSnapshotForDeath(t *testing.T) {
	s, _ := spawnService(t)
	s.bw = nil
	s.nativeOccupancyComplete = true
	s.navigationMask = world.NavigationMask{Width: 128, Height: 128, Bits: make([]byte, 128*4*128*4/8)}
	s.scenario = &world.Scenario{Version: 2, ID: "recovery", SpawnZones: map[string]world.SpawnZone{
		"east": {Tiles: [][2]int{{43, 56}}}}, Waves: []world.ScenarioWave{{ID: "first",
		Trigger: world.WaveTrigger{Type: "on_ready"}, Groups: []world.WaveGroup{{UnitType: "zerg_zergling", Count: 1, SpawnZone: "east"}}}}}
	if err := s.initScenarioRuntime(); err != nil {
		t.Fatal(err)
	}
	s.advanceScenarioRuntime(100, 1, nil)
	id := s.spawns.Order[0]
	execute, _ := s.spawns.Next()
	if err := s.spawns.Issue(execute); err != nil {
		t.Fatal(err)
	}
	if err := s.spawns.Created(id, 0, "openbw:3001", 1424, 1808); err != nil {
		t.Fatal(err)
	}
	if err := s.spawns.Ready(id, 0, "openbw:3001"); err != nil {
		t.Fatal(err)
	}
	s.advanceScenarioRuntime(101, 2, map[string]bool{"openbw:3001": true})
	s.advanceScenarioRuntime(102, 3, nil)
	if s.runtime.Waves[0].State == "cleared" {
		t.Fatal("connection gap was treated as death")
	}
	s.actorReconcileComplete = true
	s.reconciledActors = map[string]bool{}
	s.advanceScenarioRuntime(103, 4, nil)
	if s.runtime.Waves[0].State != "cleared" {
		t.Fatalf("native reconciliation plus complete snapshot did not confirm death: %+v", s.runtime.Waves[0])
	}
}
