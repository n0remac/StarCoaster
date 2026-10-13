package main

import (
	"encoding/json"
	"net"
	"path/filepath"
	"testing"

	"starcoaster/internal/world"
)

func spawnService(t *testing.T) (*service, net.Conn) {
	t.Helper()
	s := testService()
	if err := s.registry.Replace("session-a", 1, 64, 64, nil, nil); err != nil {
		t.Fatal(err)
	}
	s.transform = world.Fit(64, 64, 128, 128)
	s.ready = true
	s.lastMarines, s.lastZerglings = 6, 5
	s.actors = world.NewActorRegistry("session-a")
	s.spawnJournalPath = filepath.Join(t.TempDir(), "spawns.json")
	s.initSpawns("session-a")
	bridge, native := net.Pipe()
	s.bw = &peer{Conn: bridge}
	s.controller = &peer{}
	t.Cleanup(func() { bridge.Close(); native.Close() })
	return s, native
}

func TestBridgeSpawnRequestIssuesOnceAndReportsNativeFailure(t *testing.T) {
	s, native := spawnService(t)
	request := world.SpawnRequest{RequestID: "session-a:reinforce-1", UnitType: "terran_marine",
		Count: 1, X: 960, Y: 1024, Formation: "compact", PlayerID: 2}
	issued := make(chan world.Envelope, 1)
	go func() {
		var message world.Envelope
		_ = json.Unmarshal([]byte(readLine(native)), &message)
		issued <- message
	}()
	s.parkMessage(nil, world.Message("unit.spawn.request", "session-a", "park:spawn", "openrct2", 1, request))
	message := <-issued
	if message.Kind != "unit.spawn.execute" {
		t.Fatalf("unexpected native message: %+v", message)
	}
	var execute world.SpawnExecute
	if err := message.Decode(&execute); err != nil {
		t.Fatal(err)
	}
	if execute.X != 1984 || execute.Y != 2048 || execute.RequestID != request.RequestID {
		t.Fatalf("wrong transformed execution: %+v", execute)
	}
	s.parkMessage(nil, world.Message("unit.spawn.request", "session-a", "park:retry", "openrct2", 1, request))
	if len(s.spawnOps) != 1 {
		t.Fatal("retry issued another native creation")
	}
	s.bwMessage(nil, world.Message("world.ack", "session-a", "bw:rejected", "openbw", 1,
		world.Ack{OpID: message.OpID, Accepted: false, Error: "occupied"}))
	status, _ := s.spawns.Lookup(request.RequestID)
	if status.State != "failed" || status.Units[0].Reason != "occupied" {
		t.Fatalf("native rejection was lost: %+v", status)
	}
}

func TestBridgeSpawnRejectsInvalidInputAndRecoversUncertainJournal(t *testing.T) {
	s, _ := spawnService(t)
	request := world.SpawnRequest{RequestID: "one", UnitType: "terran_marine", Count: 1,
		X: 3000, Y: 20, Formation: "compact", PlayerID: 2}
	s.parkMessage(nil, world.Message("unit.spawn.request", "session-a", "park:outside", "openrct2", 1, request))
	if _, ok := s.spawns.Lookup(request.RequestID); ok {
		t.Fatal("out-of-bounds request queued")
	}
	request.X = 100
	request.UnitType = "zerg_zergling"
	s.parkMessage(nil, world.Message("unit.spawn.request", "session-a", "park:enemy", "openrct2", 1, request))
	if _, ok := s.spawns.Lookup(request.RequestID); ok {
		t.Fatal("player enemy request queued")
	}
	request.UnitType = "terran_marine"
	if _, err := s.spawns.Submit("session-a", request); err != nil {
		t.Fatal(err)
	}
	execute, _ := s.spawns.Next()
	if err := s.spawns.Issue(execute); err != nil {
		t.Fatal(err)
	}
	s.saveSpawns()
	recovered := testService()
	recovered.spawnJournalPath = s.spawnJournalPath
	recovered.initSpawns("session-a")
	status, ok := recovered.spawns.Lookup(request.RequestID)
	if !ok || status.State != "uncertain" {
		t.Fatalf("unsafe journal recovery: %+v %t", status, ok)
	}
	if _, ok := recovered.spawns.Next(); ok {
		t.Fatal("recovered uncertain creation was retried")
	}
}
