package main

import (
	"path/filepath"
	"testing"

	"starcoaster/internal/world"
)

func defenseService(t *testing.T) *service {
	t.Helper()
	const session = "0123456789abcdef0123456789abcdef"
	s := testService()
	if err := s.registry.Replace(session, 1, 64, 64, nil, nil); err != nil {
		t.Fatal(err)
	}
	s.transform, _ = world.Fit(64, 64, 128, 128)
	s.scenario = &world.Scenario{Version: 2, ID: "park", Mode: "park_defense", ParkSize: [2]int{64, 64},
		ParkDefense: &world.ParkDefenseWaves{InitialDelayFrames: 2880, IntervalFrames: 2880,
			ManualCooldownFrames: 360, ManualActivation: true, FixedSpawn: true,
			WaveTiers: []world.WaveTier{{FromWave: 1, Groups: []world.WaveTierGroup{{UnitType: "zerg_zergling", Count: 8}}}}}}
	s.spawns = world.NewSpawnQueue(session, 64)
	s.spawnJournalPath = filepath.Join(t.TempDir(), "spawns.json")
	s.runtime = world.NewScenarioRuntime(s.scenario, session)
	if err := s.runtime.AcceptFrame(100, 1, true); err != nil {
		t.Fatal(err)
	}
	s.ready = true
	s.bw, s.controller = &peer{}, &peer{}
	s.nativeOccupancyComplete = true
	s.navigationMask = world.NavigationMask{Width: 128, Height: 128, Bits: make([]byte, 128*4*128*4/8)}
	return s
}

func TestDefenseConfigPersistsAndKeepsOneFixedZone(t *testing.T) {
	s := defenseService(t)
	session := s.registry.Session
	enabled := true
	anchor := [2]int{4, 30}
	badAnchor, interval := [2]int{30, 30}, 90
	s.parkDefenseConfig(nil, world.Message("scenario.defense.request", session, "invalid-combined", "openrct2", 1,
		defenseConfigRequest{PlayerID: 2, CommanderID: 2, Anchor: &badAnchor, IntervalSeconds: &interval}))
	if s.runtime.WaveIntervalFrames != 0 || s.runtime.SpawnAnchor != nil {
		t.Fatal("rejected combined request changed runtime settings")
	}
	if s.runtime.Trigger(s.scenario) || s.runtime.NextAutomaticFrame != 0 {
		t.Fatal("disabled defense scheduled a wave")
	}
	request := defenseConfigRequest{PlayerID: 2, CommanderID: 3, Enabled: &enabled, Anchor: &anchor}
	s.parkDefenseConfig(nil, world.Message("scenario.defense.request", session, "bad", "openrct2", 1, request))
	if s.runtime.SpawnAnchor != nil {
		t.Fatal("unauthorized client selected spawn")
	}
	request.CommanderID = 2
	s.parkDefenseConfig(nil, world.Message("scenario.defense.request", session, "good", "openrct2", 1, request))
	if !s.runtime.DefenseEnabled || s.runtime.NextAutomaticFrame != 2980 || len(s.runtime.FixedSpawnZone.Tiles) < 4 {
		t.Fatalf("defense was not configured: %+v", s.runtime)
	}
	s.parkDefenseConfig(nil, world.Message("scenario.defense.request", session, "repeat", "openrct2", 1, request))
	if s.runtime.NextAutomaticFrame != 2980 {
		t.Fatal("idempotent enable reset countdown")
	}
	difficulty := "hard"
	s.parkDefenseConfig(nil, world.Message("scenario.defense.request", session, "settings", "openrct2", 1,
		defenseConfigRequest{PlayerID: 2, CommanderID: 2, IntervalSeconds: &interval, Difficulty: &difficulty}))
	if s.runtime.WaveIntervalFrames != 2160 || s.runtime.WaveDifficulty != "hard" ||
		s.runtime.NextAutomaticFrame != 2980 {
		t.Fatal("wave settings did not persist without resetting preparation")
	}
	s.runtime.LastFrame = 2979
	if s.runtime.Trigger(s.scenario) {
		t.Fatal("wave started before preparation ended")
	}
	s.runtime.LastFrame = 2980
	if !s.runtime.Trigger(s.scenario) || len(s.runtime.Waves) != 1 {
		t.Fatal("first wave missing")
	}
	first := s.runtime.Waves[0]
	if len(first.Units) != 12 || first.Composition[0].Count != 12 || s.runtime.NextAutomaticFrame != 5140 {
		t.Fatal("hard wave composition or configured interval missing")
	}
	if first.SpawnZone != "selected" || len(first.FixedZone.Tiles) != len(s.runtime.FixedSpawnZone.Tiles) {
		t.Fatal("wave did not preserve selected zone")
	}
	disabled := false
	s.parkDefenseConfig(nil, world.Message("scenario.defense.request", session, "disable", "openrct2", 1,
		defenseConfigRequest{PlayerID: 2, CommanderID: 2, Enabled: &disabled}))
	if s.runtime.DefenseEnabled || s.runtime.NextAutomaticFrame != 0 {
		t.Fatal("disable did not stop schedule")
	}
	s.runtime.LastFrame += 10000
	if s.runtime.Trigger(s.scenario) || len(s.runtime.Waves) != 1 {
		t.Fatal("disabled defense started another wave")
	}
	if _, err := s.runtime.RequestManual(s.scenario, "manual", 2, 1); err == nil {
		t.Fatal("manual wave accepted while disabled")
	}
	if err := s.runtime.Validate(s.scenario, session); err != nil {
		t.Fatal(err)
	}
	restarted := defenseService(t)
	restarted.registry = s.registry
	restarted.scenario = s.scenario
	restarted.spawnJournalPath = s.spawnJournalPath
	restarted.runtime = nil
	if err := restarted.initScenarioRuntime(); err != nil {
		t.Fatal(err)
	}
	if restarted.runtime.TotalTriggered != 1 || restarted.runtime.DefenseEnabled {
		t.Fatal("restart lost defense state or wave sequence")
	}
}

func TestDefenseSpawnPointRejectsInteriorAndBlockedTiles(t *testing.T) {
	s := defenseService(t)
	if _, err := s.fixedDefenseZone([2]int{30, 30}); err == nil {
		t.Fatal("interior anchor accepted")
	}
	anchorX, anchorY := s.transform.X(4*32+16), s.transform.Y(30*32+16)
	s.nativeOccupants = []world.NativeOccupant{{X: anchorX, Y: anchorY}}
	if _, err := s.fixedDefenseZone([2]int{4, 30}); err == nil {
		t.Fatal("occupied anchor accepted because its neighbors were clear")
	}
	s.nativeOccupants = nil
	for y := 26; y <= 34; y++ {
		for x := 2; x <= 8; x++ {
			nativeX := s.transform.X(x*32 + 16)
			nativeY := s.transform.Y(y*32 + 16)
			for dy := -16; dy <= 16; dy += 4 {
				for dx := -16; dx <= 16; dx += 4 {
					ix, iy := (nativeX+dx)/8, (nativeY+dy)/8
					index := iy*s.navigationMask.Width*4 + ix
					if index >= 0 && index < len(s.navigationMask.Bits)*8 {
						s.navigationMask.Bits[index/8] |= 1 << (index % 8)
					}
				}
			}
		}
	}
	if _, err := s.fixedDefenseZone([2]int{4, 30}); err == nil {
		t.Fatal("blocked anchor accepted")
	}
}

func TestDefenseEscalationKeepsSelectedZone(t *testing.T) {
	s := defenseService(t)
	s.scenario.ParkDefense.WaveTiers = []world.WaveTier{
		{FromWave: 1, Groups: []world.WaveTierGroup{{UnitType: "zerg_zergling", Count: 8}}},
		{FromWave: 3, Groups: []world.WaveTierGroup{{UnitType: "zerg_zergling", Count: 7}, {UnitType: "zerg_hydralisk", Count: 2}}},
		{FromWave: 6, Groups: []world.WaveTierGroup{{UnitType: "zerg_zergling", Count: 7}, {UnitType: "zerg_hydralisk", Count: 2}, {UnitType: "zerg_ultralisk", Count: 1}}},
	}
	enabled, anchor := true, [2]int{4, 30}
	s.parkDefenseConfig(nil, world.Message("scenario.defense.request", s.registry.Session, "enable", "openrct2", 1,
		defenseConfigRequest{PlayerID: 2, CommanderID: 2, Enabled: &enabled, Anchor: &anchor}))
	if !s.runtime.DefenseEnabled {
		t.Fatal("defense was not enabled")
	}
	wantTypes := []map[string]int{
		{"zerg_zergling": 8}, {"zerg_zergling": 8},
		{"zerg_zergling": 7, "zerg_hydralisk": 2},
		{"zerg_zergling": 7, "zerg_hydralisk": 2},
		{"zerg_zergling": 7, "zerg_hydralisk": 2},
		{"zerg_zergling": 7, "zerg_hydralisk": 2, "zerg_ultralisk": 1},
	}
	for index, expected := range wantTypes {
		s.runtime.LastFrame = s.runtime.NextAutomaticFrame
		if !s.runtime.Trigger(s.scenario) {
			t.Fatalf("wave %d was not scheduled", index+1)
		}
		wave := &s.runtime.Waves[index]
		if wave.SpawnZone != "selected" || len(wave.FixedZone.Tiles) != len(s.runtime.FixedSpawnZone.Tiles) {
			t.Fatalf("wave %d lost its fixed zone", index+1)
		}
		for tileIndex, tile := range wave.FixedZone.Tiles {
			if tile != s.runtime.FixedSpawnZone.Tiles[tileIndex] {
				t.Fatalf("wave %d changed spawn tile %d", index+1, tileIndex)
			}
		}
		counts := map[string]int{}
		for _, unit := range wave.Units {
			counts[unit.UnitType]++
		}
		if len(counts) != len(expected) {
			t.Fatalf("wave %d composition: %v", index+1, counts)
		}
		for kind, count := range expected {
			if counts[kind] != count {
				t.Fatalf("wave %d composition: %v", index+1, counts)
			}
		}
		wave.State = "active"
	}
}
