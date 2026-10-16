package main

import (
	"fmt"
	"path/filepath"
	"testing"

	"starcoaster/internal/world"
)

func TestBridgeManualWaveAuthorizationIdempotencyAndDeadline(t *testing.T) {
	const session = "0123456789abcdef0123456789abcdef"
	s := testService()
	if err := s.registry.Replace(session, 1, 64, 64, nil, nil); err != nil {
		t.Fatal(err)
	}
	s.transform, _ = world.Fit(64, 64, 128, 128)
	s.scenario = &world.Scenario{Version: 2, ID: "park", Mode: "park_defense", ParkSize: [2]int{64, 64},
		SpawnZones: map[string]world.SpawnZone{
			"north": {Tiles: [][2]int{{20, 20}, {21, 20}}},
			"south": {Tiles: [][2]int{{20, 40}, {21, 40}}},
		}, ParkDefense: &world.ParkDefenseWaves{InitialDelayFrames: 2880, IntervalFrames: 2880,
			UnitsPerWave: 8, ManualCooldownFrames: 360, SpawnZones: []string{"north", "south"}}}
	s.spawns = world.NewSpawnQueue(session, 64)
	s.spawnJournalPath = filepath.Join(t.TempDir(), "spawns.json")
	s.runtime = world.NewScenarioRuntime(s.scenario, session)
	if err := s.runtime.AcceptFrame(100, 1, true); err != nil {
		t.Fatal(err)
	}
	s.runtime.Trigger(s.scenario)
	s.ready = true
	s.bw, s.controller = &peer{}, &peer{}
	s.nativeOccupancyComplete = true
	s.navigationMask = world.NavigationMask{Width: 128, Height: 128, Bits: make([]byte, 128*4*128*4/8)}
	request := scenarioWaveRequest{RequestID: fmt.Sprintf("%s:wave:2:1", session), PlayerID: 2, CommanderID: 2}
	message := world.Message("scenario.wave.request", session, "park:manual", "openrct2", 1, request)
	deadline := s.runtime.NextAutomaticFrame
	s.parkWaveRequest(nil, message)
	if len(s.runtime.Waves) != 1 || s.runtime.Waves[0].Origin != "manual" || s.runtime.NextAutomaticFrame != deadline {
		t.Fatalf("manual wave changed schedule or failed: %+v", s.runtime)
	}
	s.parkWaveRequest(nil, message)
	if len(s.runtime.Waves) != 1 {
		t.Fatal("duplicate manual request created a wave")
	}
	request.RequestID = fmt.Sprintf("%s:wave:2:2", session)
	s.parkWaveRequest(nil, world.Message("scenario.wave.request", session, "park:cooldown", "openrct2", 1, request))
	if len(s.runtime.Waves) != 1 {
		t.Fatal("cooldown did not reject a second wave")
	}
	s.runtime.LastFrame = 500
	request.CommanderID = 3
	s.parkWaveRequest(nil, world.Message("scenario.wave.request", session, "park:unauthorized", "openrct2", 1, request))
	if len(s.runtime.Waves) != 1 {
		t.Fatal("non-commander created a wave")
	}
	request.CommanderID = 2
	s.parkWaveRequest(nil, world.Message("scenario.wave.request", session, "park:stale", "openrct2", 2, request))
	if len(s.runtime.Waves) != 1 {
		t.Fatal("stale revision created a wave")
	}
	s.controller = nil
	s.parkWaveRequest(nil, world.Message("scenario.wave.request", session, "park:disconnected", "openrct2", 1, request))
	if len(s.runtime.Waves) != 1 {
		t.Fatal("disconnected controller accepted a wave")
	}
	s.controller = &peer{}
	s.lastMarines = 237
	s.parkWaveRequest(nil, world.Message("scenario.wave.request", session, "park:capacity", "openrct2", 1, request))
	if len(s.runtime.Waves) != 1 {
		t.Fatal("actor limit accepted a wave")
	}
	s.lastMarines = 5
	s.parkWaveRequest(nil, world.Message("scenario.wave.request", session, "park:second", "openrct2", 1, request))
	if len(s.runtime.Waves) != 2 || s.runtime.NextAutomaticFrame != deadline {
		t.Fatal("eligible manual wave did not queue independently")
	}
}
