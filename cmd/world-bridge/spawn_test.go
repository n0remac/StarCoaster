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
	s.transform, _ = world.Fit(64, 64, 128, 128)
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

func TestActiveActorCountIncludesTrainedTypes(t *testing.T) {
	s := &service{lastMarines: 5, lastZerglings: 3}
	if got := s.activeActorCount(); got != 8 {
		t.Fatalf("legacy count before a complete snapshot: %d", got)
	}
	s.lastNativeActors = 11 // Includes a Firebat, Medic, and Goliath.
	if got := s.activeActorCount(); got != 11 {
		t.Fatalf("trained actors were omitted from spawn capacity: %d", got)
	}
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

func TestBridgeSpawnBecomesReadyOnlyAfterBothNativeBindings(t *testing.T) {
	s, _ := spawnService(t)
	s.controller = nil
	request := world.SpawnRequest{RequestID: "bind-both", UnitType: "terran_marine", Count: 1,
		X: 100, Y: 100, Formation: "compact", PlayerID: 1}
	if _, err := s.spawns.Submit("session-a", request); err != nil {
		t.Fatal(err)
	}
	execute, _ := s.spawns.Next()
	if err := s.spawns.Issue(execute); err != nil {
		t.Fatal(err)
	}
	identity := world.ActorIdentity{ID: "openbw:3001", Engine: "openbw", Type: "terran_marine",
		Owner: 1, Generation: 1, Session: "session-a"}
	if err := s.actors.Spawn(identity); err != nil {
		t.Fatal(err)
	}
	publisher := world.ActorBinding{ID: identity.ID, Session: identity.Session,
		Generation: 1, Participant: "publisher", NativeID: "50", CreationFrame: 110}
	if err := s.actors.Bind(publisher); err != nil {
		t.Fatal(err)
	}
	s.bwSpawnMessage(nil, world.Message("unit.spawn.status", "session-a", "bw:created", "openbw", 1,
		nativeSpawnStatus{RequestID: request.RequestID, Index: 0, State: "created",
			ActorID: identity.ID, X: 1680, Y: 2000}))
	if status, _ := s.spawns.Lookup(request.RequestID); status.State != "created" {
		t.Fatalf("publisher binding made spawn ready: %+v", status)
	}
	controller := publisher
	controller.Participant, controller.NativeID = "controller", "71"
	s.controllerMessage(nil, world.Message("actor.bind", "session-a", "controller:bind", "openbw", 1, controller))
	if status, _ := s.spawns.Lookup(request.RequestID); status.State != "ready" ||
		status.Units[0].ActorID != identity.ID {
		t.Fatalf("matching controller did not ready spawn: %+v", status)
	}
}

func TestScenarioZergWaveUsesSameNativeQueue(t *testing.T) {
	s, native := spawnService(t)
	s.scenario = &world.Scenario{SpawnWaves: []world.SpawnWave{{ID: "wave-one", Trigger: "on_ready",
		UnitType: "zerg_zergling", Count: 5, X: 1424, Y: 1808, Formation: "compact"}}}
	s.submitScenarioSpawns()
	s.submitScenarioSpawns()
	if s.spawns.PendingCount() != 5 {
		t.Fatal("replayed scenario wave created another batch")
	}
	issued := make(chan world.Envelope, 1)
	go func() {
		var message world.Envelope
		_ = json.Unmarshal([]byte(readLine(native)), &message)
		issued <- message
	}()
	s.pumpSpawns()
	message := <-issued
	var execute world.SpawnExecute
	if message.Kind != "unit.spawn.execute" || message.Decode(&execute) != nil ||
		execute.UnitType != "zerg_zergling" || execute.Index != 0 {
		t.Fatalf("scenario wave bypassed shared queue: %+v %+v", message, execute)
	}
}

func TestScenarioZoneReservesManualMarineRequests(t *testing.T) {
	s, _ := spawnService(t)
	s.nativeOccupancyComplete = true
	s.navigationMask = world.NavigationMask{Width: 128, Height: 128, Bits: make([]byte, 128*4*128*4/8)}
	zone := world.SpawnZone{Tiles: [][2]int{{43, 56}, {44, 56}, {45, 56}}}
	first := world.Point{X: 43*32 + 16, Y: 56*32 + 16}
	request := world.SpawnRequest{RequestID: "manual-marine", UnitType: "terran_marine", Count: 1,
		X: first.X, Y: first.Y, Formation: "compact", PlayerID: 1}
	if _, err := s.spawns.Submit("session-a", request); err != nil {
		t.Fatal(err)
	}
	s.nativeOccupants = []world.NativeOccupant{{X: s.transform.X(44*32 + 16), Y: s.transform.Y(56*32 + 16)}}
	if got, ok := s.scenarioZoneCandidate(zone, nil); !ok || got != (world.Point{X: 45*32 + 16, Y: 56*32 + 16}) {
		t.Fatalf("native occupancy or manual reservation ignored: %v %v", got, ok)
	}
	s.nativeOccupancyComplete = false
	if _, ok := s.scenarioZoneCandidate(zone, nil); ok {
		t.Fatal("incomplete native occupancy accepted")
	}
}

func TestScenarioZoneReleasesReadyActorOriginalTile(t *testing.T) {
	s, _ := spawnService(t)
	s.nativeOccupancyComplete = true
	s.navigationMask = world.NavigationMask{Width: 128, Height: 128, Bits: make([]byte, 128*4*128*4/8)}
	position := world.Point{X: 43*32 + 16, Y: 56*32 + 16}
	zone := world.SpawnZone{Tiles: [][2]int{{43, 56}}}
	request := world.SpawnRequest{RequestID: "settled-zergling", UnitType: "zerg_zergling",
		Count: 1, X: position.X, Y: position.Y, Formation: "compact", PlayerID: 0}
	if _, err := s.spawns.Submit("session-a", request); err != nil {
		t.Fatal(err)
	}
	execute, _ := s.spawns.Next()
	if err := s.spawns.Issue(execute); err != nil {
		t.Fatal(err)
	}
	if err := s.spawns.Created(request.RequestID, 0, "openbw:3001", position.X, position.Y); err != nil {
		t.Fatal(err)
	}
	if err := s.spawns.Ready(request.RequestID, 0, "openbw:3001"); err != nil {
		t.Fatal(err)
	}
	if got, ok := s.scenarioZoneCandidate(zone, nil); !ok || got != position {
		t.Fatalf("settled actor permanently reserved spawn tile: %v %v", got, ok)
	}
}

func TestDisconnectedClientCanQueryCompletedSpawnStatus(t *testing.T) {
	s, _ := spawnService(t)
	s.park = nil
	request := world.SpawnRequest{RequestID: "recover-client", UnitType: "terran_marine", Count: 1,
		X: 100, Y: 100, Formation: "compact", PlayerID: 1}
	if _, err := s.spawns.Submit("session-a", request); err != nil {
		t.Fatal(err)
	}
	execute, _ := s.spawns.Next()
	if err := s.spawns.Issue(execute); err != nil {
		t.Fatal(err)
	}
	if err := s.spawns.Fail(request.RequestID, 0, "native_rejected"); err != nil {
		t.Fatal(err)
	}
	s.saveSpawns()
	s.spawnStatus(world.SpawnStatus{RequestID: request.RequestID, State: "failed"})
	bridge, client := net.Pipe()
	defer bridge.Close()
	defer client.Close()
	s.park = &peer{Conn: bridge}
	received := make(chan []world.Envelope, 1)
	go func() {
		var messages []world.Envelope
		for i := 0; i < 2; i++ {
			var message world.Envelope
			_ = json.Unmarshal([]byte(readLine(client)), &message)
			messages = append(messages, message)
		}
		received <- messages
	}()
	s.parkSpawnMessage(s.park, world.Message("unit.spawn.query", "session-a", "park:query", "openrct2", 1,
		map[string]string{"request_id": request.RequestID}))
	messages := <-received
	if messages[0].Kind != "world.ack" || messages[1].Kind != "unit.spawn.status" {
		t.Fatalf("query response: %+v", messages)
	}
	var status world.SpawnStatus
	if err := messages[1].Decode(&status); err != nil || status.State != "failed" ||
		status.Units[0].Reason != "native_rejected" {
		t.Fatalf("recovered status: %+v %v", status, err)
	}
}
