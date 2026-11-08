package main

import (
	"encoding/json"
	"io"
	"net"
	"os"
	"path/filepath"
	"testing"

	"starcoaster/internal/world"
)

func enemyAssaultService(t *testing.T) *service {
	t.Helper()
	s := testService()
	const session = "test-enemy-assault"
	if err := s.registry.Replace(session, 1, 64, 64, nil, nil); err != nil {
		t.Fatal(err)
	}
	s.transform, _ = world.Fit(64, 64, 128, 128)
	s.scenario = &world.Scenario{Version: 2, ID: "generated", Mode: "park_defense", ParkSize: [2]int{64, 64},
		ParkDefense: &world.ParkDefenseWaves{SpawnPolicy: "base_production", InitialDelayFrames: 7200,
			IntervalFrames: 2880, WaveTiers: []world.WaveTier{{FromWave: 1,
				Groups: []world.WaveTierGroup{{UnitType: "zerg_zergling", Count: 8}}}}},
		EnemyBase: &world.ScenarioEnemyBase{Version: 2, LayoutState: "ready", MaxTrainOrders: 6,
			TerranApproachTile: []int{24, 24}}}
	s.runtime = world.NewScenarioRuntime(s.scenario, session)
	s.runtime.Started, s.runtime.EconomyReadyFrame = true, 1
	s.runtime.NextAutomaticFrame = 7201
	s.runtime.EnemyAssault.BindColony(5)
	s.actors = world.NewActorRegistry(session)
	for i := 1; i <= 2; i++ {
		id := "openbw:300" + string(rune('0'+i))
		identity := world.ActorIdentity{ID: id, Engine: "openbw", Type: "zerg_zergling",
			Owner: 0, Phase: "complete", Generation: uint64(i), Session: session}
		if err := s.actors.Spawn(identity); err != nil {
			t.Fatal(err)
		}
		for _, role := range []string{"publisher", "controller"} {
			if err := s.actors.Bind(world.ActorBinding{ID: id, Session: session,
				Generation: uint64(i), Participant: role, NativeID: string(rune('0' + i + 4)),
				CreationFrame: 100}); err != nil {
				t.Fatal(err)
			}
		}
	}
	s.ready, s.actorReconcileComplete = true, true
	s.spawnJournalPath = filepath.Join(t.TempDir(), "spawns.json")
	for _, role := range []string{"publisher", "controller"} {
		bridge, sink := net.Pipe()
		t.Cleanup(func() { bridge.Close(); sink.Close() })
		go io.Copy(io.Discard, sink)
		if role == "publisher" {
			s.bw = &peer{Conn: bridge}
		} else {
			s.controller = &peer{Conn: bridge}
		}
	}
	return s
}

func TestEnemyAssaultServiceDispatchesObservedShortGroupOnce(t *testing.T) {
	s := enemyAssaultService(t)
	living := map[string]bool{"openbw:3001": true, "openbw:3002": true}
	s.advanceEnemyAssault(7201, living)
	if len(s.runtime.EnemyAssault.Waves) != 1 || len(s.runtime.EnemyAssault.Waves[0].Actors) != 2 ||
		s.runtime.EnemyAssault.Waves[0].Desired != 8 || s.runtime.TotalTriggered != 1 {
		t.Fatalf("wrong native assignment: %+v", s.runtime.EnemyAssault)
	}
	s.advanceEnemyAssault(7202, living)
	if len(s.runtime.EnemyAssault.Waves) != 1 {
		t.Fatal("duplicate snapshot created another wave")
	}
	data, err := os.ReadFile(s.spawnJournalPath + ".scenario.json")
	if err != nil {
		t.Fatal(err)
	}
	var stored world.ScenarioRuntime
	if err := json.Unmarshal(data, &stored); err != nil || len(stored.EnemyAssault.Waves) != 1 {
		t.Fatal("assignment not durable before native send", err)
	}
}

func TestEnemyAssaultServiceRequiresLivingHatcheryButNotPool(t *testing.T) {
	living := map[string]bool{"openbw:3001": true, "openbw:3002": true}
	s := enemyAssaultService(t)
	s.registry.Destroyed["scenario:enemy-spawning-pool"] = true
	s.advanceEnemyAssault(7201, living)
	if len(s.runtime.EnemyAssault.Waves) != 1 {
		t.Fatal("destroyed Pool erased existing native fighters")
	}
	s = enemyAssaultService(t)
	s.registry.Destroyed["scenario:enemy-hatchery"] = true
	s.advanceEnemyAssault(7201, living)
	if len(s.runtime.EnemyAssault.Waves) != 0 {
		t.Fatal("dead Hatchery launched a new wave")
	}
}

func TestEnemyAssaultServiceToggleWaitsFreshCountdown(t *testing.T) {
	s := enemyAssaultService(t)
	living := map[string]bool{"openbw:3001": true, "openbw:3002": true}
	s.runtime.DefenseEnabled = false
	s.advanceEnemyAssault(7201, living)
	if len(s.runtime.EnemyAssault.Waves) != 0 {
		t.Fatal("disabled defense assigned native actors")
	}
	s.runtime.DefenseEnabled = true
	s.runtime.NextAutomaticFrame = 7201 + 7200
	s.advanceEnemyAssault(7202, living)
	if len(s.runtime.EnemyAssault.Waves) != 0 {
		t.Fatal("reenable caught up previous deadline")
	}
}

func TestEnemyAssaultJournalReconnectAndB2Migration(t *testing.T) {
	s := enemyAssaultService(t)
	living := map[string]bool{"openbw:3001": true, "openbw:3002": true}
	s.advanceEnemyAssault(7201, living)
	wave := s.runtime.EnemyAssault.Waves[0]
	if !s.runtime.EnemyAssault.Resolve(wave.Attempts[0].RequestID, true, "", 7202) ||
		!s.saveScenarioRuntime() {
		t.Fatal("could not persist accepted native order")
	}
	s.runtime = nil
	if err := s.initScenarioRuntime(); err != nil {
		t.Fatal(err)
	}
	if len(s.runtime.EnemyAssault.Waves) != 1 ||
		s.runtime.EnemyAssault.Waves[0].State != "ordered" {
		t.Fatal("reconnect lost accepted order")
	}
	s.advanceEnemyAssault(7203, living)
	if len(s.runtime.EnemyAssault.Waves) != 1 {
		t.Fatal("reconnect duplicated wave")
	}
	s.runtime.EnemyAssault = nil // B2 journal from this same session and definition.
	s.runtime.JournalVersion = 2
	s.runtime.TotalTriggered = 0
	s.runtime.NextWaveSequence = 1
	if !s.saveScenarioRuntime() {
		t.Fatal("could not persist B2 fixture")
	}
	s.runtime = nil
	if err := s.initScenarioRuntime(); err != nil {
		t.Fatal(err)
	}
	if s.runtime.JournalVersion != 3 || s.runtime.EnemyAssault == nil ||
		len(s.runtime.EnemyAssault.Waves) != 0 {
		t.Fatal("B2 journal migration failed")
	}
}
