package main

import (
	"bufio"
	"encoding/json"
	"io"
	"net"
	"testing"
	"time"

	"starcoaster/internal/world"
)

func testService() *service {
	return &service{registry: world.NewRegistry(), mapping: world.DefaultMapping(), pending: map[string]world.CombatEvent{}, proxies: map[string]string{}}
}

func TestSameSessionSnapshotReplaysPendingCombatDemolition(t *testing.T) {
	s := testService()
	entity := world.Entity{ID: "scenario:western-hatchery", Source: "openrct2",
		SourceID: "large_scenery:7:256:992", Kind: "structure", Type: "zerg_hatchery", Owner: 0,
		Position: world.Point{X: 64, Y: 96}, Elevation: 112,
		Geometry: world.Geometry{Cells: []world.Point{{X: 2, Y: 3}},
			Rects: []world.Rect{{X: 64, Y: 96, Width: 32, Height: 32}}},
		Destructible: true, Combat: world.Combat{Targetable: true, Health: 1250}, Revision: 1}
	if err := s.registry.Replace("session-a", 1, 8, 8, []world.Entity{entity}, nil); err != nil {
		t.Fatal(err)
	}
	event := world.CombatEvent{ID: "session-a:100:destruction:1", EntityID: entity.ID,
		ProxyID: "openbw:8", Type: "destruction", Health: 0}
	s.pending[event.ID] = event
	s.pendingFrames = map[string]int{event.ID: 100}
	s.proxies[entity.ID] = event.ProxyID
	s.parkMessage(nil, world.Message("world.snapshot.begin", "session-a", "begin", "openrct2", 1,
		world.SnapshotBegin{Width: 8, Height: 8, Chunks: 1}))
	s.parkMessage(nil, world.Message("world.snapshot.chunk", "session-a", "chunk", "openrct2", 1,
		world.SnapshotChunk{Index: 0, Entities: []world.Entity{entity}}))
	s.parkMessage(nil, world.Message("world.snapshot.end", "session-a", "end", "openrct2", 1,
		world.SnapshotEnd{Entities: 1}))
	if s.pending[event.ID] != event || s.pendingFrames[event.ID] != 100 {
		t.Fatal("same-session snapshot discarded a native destruction awaiting park removal")
	}
	bridge, park := net.Pipe()
	defer bridge.Close()
	defer park.Close()
	s.park = &peer{Conn: bridge}
	s.controller = &peer{}
	s.publisherNavigationReady, s.controllerNavigationReady, s.actorReconcileComplete = true, true, true
	s.pendingReady = &world.Ready{}
	forwarded := make(chan []world.Envelope, 1)
	go func() {
		messages := make([]world.Envelope, 2)
		for index := range messages {
			_ = json.Unmarshal([]byte(readLine(park)), &messages[index])
		}
		forwarded <- messages
	}()
	s.publishReady()
	select {
	case messages := <-forwarded:
		if messages[0].Kind != "world.ready" || messages[1].Kind != "combat.event" ||
			messages[1].Session != "session-a" || messages[1].Revision != 1 {
			t.Fatalf("pending demolition not replayed after readiness: %+v", messages)
		}
		var replay world.CombatEvent
		if err := messages[1].Decode(&replay); err != nil || replay != event {
			t.Fatalf("wrong replayed demolition: %+v, %v", replay, err)
		}
	case <-time.After(time.Second):
		t.Fatal("pending demolition replay timed out")
	}
}

func TestParkPatchStagesWithoutAdvancingConfirmedWorld(t *testing.T) {
	s := testService()
	if err := s.registry.Replace("session-a", 1, 8, 8, nil, nil); err != nil {
		t.Fatal(err)
	}
	transform, err := world.Fit(8, 8, 8, 8)
	if err != nil {
		t.Fatal(err)
	}
	s.transform, s.bwWidth, s.bwHeight = transform, 8, 8
	publisher, publisherSink := net.Pipe()
	controller, controllerSink := net.Pipe()
	defer publisher.Close()
	defer publisherSink.Close()
	defer controller.Close()
	defer controllerSink.Close()
	go io.Copy(io.Discard, publisherSink)
	go io.Copy(io.Discard, controllerSink)
	s.bw, s.controller, s.ready = &peer{Conn: publisher}, &peer{Conn: controller}, true
	wall := world.Entity{ID: "openrct2:wall:3:0:0:0:0#1", Source: "openrct2",
		SourceID: "wall:3:0:0:0:0", Kind: "wall", Type: "wall", Position: world.Point{X: 0, Y: 0},
		Geometry: world.Geometry{Cells: []world.Point{{X: 0, Y: 0}},
			Rects: []world.Rect{{X: 0, Y: 0, Width: 4, Height: 32}}}, Revision: 2}
	patch := world.Patch{ID: "park:patch:1", BaseRevision: 1, ResultRevision: 2,
		Additions: []world.Entity{wall}, Counts: world.PatchCounts{Additions: 1}}
	message := world.Message("world.patch", "session-a", "park:op:1", "openrct2", 2, patch)
	s.parkMessage(nil, message)
	if s.parkPatch == nil || s.parkPatch.patch.ID != patch.ID ||
		s.registry.Revision != 1 || len(s.registry.Entities) != 0 || s.parkPatch.mask.Hash == "" {
		t.Fatal("patch did not stage independently of confirmed registry")
	}
	s.parkMessage(nil, message)
	if s.parkPatch == nil || s.registry.Revision != 1 {
		t.Fatal("duplicate transport applied patch")
	}
	patch.Additions[0].Geometry.Rects[0].X = 255
	s.parkMessage(nil, world.Message("world.patch", "session-a", "park:op:2", "openrct2", 2, patch))
	if s.registry.Revision != 1 || len(s.registry.Entities) != 0 {
		t.Fatal("conflicting patch changed world")
	}
	hash := s.parkPatch.mask.Hash
	report := func(kind, participant string, frame, applyFrame int) {
		message := world.Message(kind, "session-a", "native:"+participant+kind, "openbw", 2,
			map[string]any{"hash": hash, "accepted": true, "error": "", "apply_frame": applyFrame})
		message.BWTick = frame
		if participant == "publisher" {
			s.bwMessage(nil, message)
		} else {
			s.controllerMessage(nil, message)
		}
	}
	report("navigation.mask.staged", "publisher", 100, 0)
	if s.parkPatch.applyFrame != 0 {
		t.Fatal("one staging acknowledgement scheduled both participants")
	}
	report("navigation.mask.staged", "controller", 101, 0)
	frame := s.parkPatch.applyFrame
	if frame <= 101 {
		t.Fatal("scheduled frame did not account for observed native frames")
	}
	report("navigation.mask.scheduled", "publisher", 102, frame)
	report("navigation.mask.scheduled", "controller", 103, frame)
	report("navigation.mask.applied", "publisher", frame, frame)
	if s.registry.Revision != 1 {
		t.Fatal("one applied acknowledgement committed the patch")
	}
	report("navigation.mask.applied", "controller", frame, frame)
	if s.registry.Revision != 2 || s.parkPatch != nil || !s.ready ||
		s.navigationMask.Hash != hash {
		t.Fatal("matching native application did not commit the patch")
	}
}

func TestActorLifecycleRoutingRejectsAmbiguousBindings(t *testing.T) {
	s := testService()
	if err := s.registry.Replace("session-a", 1, 8, 8, nil, nil); err != nil {
		t.Fatal(err)
	}
	s.actors = world.NewActorRegistry("session-a")
	identity := world.ActorIdentity{ID: "openbw:3001", Engine: "openbw", Type: "terran_marine",
		Owner: 1, Generation: 42, Session: "session-a"}
	s.bwMessage(nil, world.Message("actor.spawn", "session-a", "bw:spawn", "openbw", 1, identity))
	if _, found := s.actors.Lookup(identity.ID); !found {
		t.Fatal("spawn was not registered")
	}
	publisher := world.ActorBinding{ID: identity.ID, Session: "session-a", Generation: 42,
		Participant: "publisher", NativeID: "11", CreationFrame: 153}
	s.bwMessage(nil, world.Message("actor.bind", "session-a", "bw:bind", "openbw", 1, publisher))
	if s.actors.Commandable(identity.ID) {
		t.Fatal("publisher alone made actor commandable")
	}
	controller := publisher
	controller.Participant, controller.NativeID = "controller", "98"
	bridgeSide, parkSide := net.Pipe()
	defer bridgeSide.Close()
	defer parkSide.Close()
	s.park = &peer{Conn: bridgeSide}
	forwarded := make(chan world.Envelope, 1)
	go func() {
		var message world.Envelope
		_ = json.Unmarshal([]byte(readLine(parkSide)), &message)
		forwarded <- message
	}()
	s.controllerMessage(nil, world.Message("actor.bind", "session-a", "controller:bind", "openbw", 1, controller))
	if !s.actors.Commandable(identity.ID) {
		t.Fatal("both native bindings did not activate actor")
	}
	if message := <-forwarded; message.Kind != "actor.bind" || message.Session != identity.Session {
		t.Fatalf("park did not receive completed binding: %+v", message)
	}
	s.park = nil
	stale := controller
	stale.Session = "old-session"
	s.controllerMessage(nil, world.Message("actor.bind", "old-session", "controller:stale", "openbw", 1, stale))
	if record, _ := s.actors.Lookup(identity.ID); record.Bindings["controller"] != controller {
		t.Fatal("stale controller changed binding")
	}
	s.bwMessage(nil, world.Message("actor.despawn", "session-a", "bw:death", "openbw", 1,
		world.ActorDespawn{ID: identity.ID, Session: "session-a", Generation: 42}))
	if s.actors.Commandable(identity.ID) {
		t.Fatal("despawned actor remained commandable")
	}
}

func TestActorReconcileForwardsMissedDespawn(t *testing.T) {
	s := testService()
	if err := s.registry.Replace("session-a", 1, 8, 8, nil, nil); err != nil {
		t.Fatal(err)
	}
	s.actors = world.NewActorRegistry("session-a")
	identity := world.ActorIdentity{ID: "openbw:3001", Engine: "openbw", Type: "terran_marine",
		Owner: 1, Generation: 1, Session: "session-a"}
	if err := s.actors.Spawn(identity); err != nil {
		t.Fatal(err)
	}
	bridgeSide, parkSide := net.Pipe()
	defer bridgeSide.Close()
	defer parkSide.Close()
	s.park = &peer{Conn: bridgeSide}
	_ = parkSide.SetReadDeadline(time.Now().Add(time.Second))
	forwarded := make(chan world.Envelope, 1)
	go func() {
		var message world.Envelope
		_ = json.Unmarshal([]byte(readLine(parkSide)), &message)
		forwarded <- message
	}()
	s.bwMessage(nil, world.Message("actor.reconcile", "session-a", "bw:reconcile", "openbw", 1,
		world.ActorReconcile{Living: []world.ActorIdentity{}}))
	message := <-forwarded
	if message.Kind != "actor.despawn" || message.Session != identity.Session {
		t.Fatalf("missed death was not forwarded to park: %+v", message)
	}
}

func TestRuntimeCommandRequiresConfirmedBindings(t *testing.T) {
	s := testService()
	if err := s.registry.Replace("session-a", 1, 8, 8, nil, nil); err != nil {
		t.Fatal(err)
	}
	s.ready = true
	s.transform, _ = world.Fit(8, 8, 8, 8)
	s.actors = world.NewActorRegistry("session-a")
	identity := world.ActorIdentity{ID: "openbw:3001", Engine: "openbw", Type: "terran_marine",
		Owner: 1, Generation: 1, Session: "session-a"}
	if err := s.actors.Spawn(identity); err != nil {
		t.Fatal(err)
	}
	bridgeSide, controllerSide := net.Pipe()
	defer bridgeSide.Close()
	defer controllerSide.Close()
	s.controller = &peer{Conn: bridgeSide}
	command := worldCommand{CommandID: "command:1", PlayerID: 2, RequestID: 1,
		UnitIDs: []string{identity.ID}, Verb: "unit.move", X: 32, Y: 32}
	request := func(id string) {
		command.CommandID = id
		s.parkMessage(nil, world.Message("combat.command", "session-a", id, "openrct2", 1, command))
	}
	request("command:before")
	if len(s.commands) != 0 {
		t.Fatal("unbound actor command was forwarded")
	}
	publisher := world.ActorBinding{ID: identity.ID, Session: identity.Session, Generation: 1,
		Participant: "publisher", NativeID: "11", CreationFrame: 153}
	if err := s.actors.Bind(publisher); err != nil {
		t.Fatal(err)
	}
	request("command:partial")
	if len(s.commands) != 0 {
		t.Fatal("partially bound actor command was forwarded")
	}
	controller := publisher
	controller.Participant, controller.NativeID = "controller", "98"
	if err := s.actors.Bind(controller); err != nil {
		t.Fatal(err)
	}
	forwarded := make(chan world.Envelope, 1)
	go func() {
		var message world.Envelope
		_ = json.Unmarshal([]byte(readLine(controllerSide)), &message)
		forwarded <- message
	}()
	request("command:active")
	if message := <-forwarded; message.Kind != "combat.command" || len(s.commands) != 1 {
		t.Fatalf("active actor order not forwarded: %+v", message)
	}
	delete(s.commands, "command:active")
	medic := world.ActorIdentity{ID: "openbw:3002", Engine: "openbw", Type: "terran_medic",
		Owner: 1, Generation: 1, Session: "session-a"}
	if err := s.actors.Spawn(medic); err != nil {
		t.Fatal(err)
	}
	medicBinding := publisher
	medicBinding.ID, medicBinding.NativeID = medic.ID, "12"
	if err := s.actors.Bind(medicBinding); err != nil {
		t.Fatal(err)
	}
	medicBinding.Participant, medicBinding.NativeID = "controller", "99"
	if err := s.actors.Bind(medicBinding); err != nil {
		t.Fatal(err)
	}
	command = worldCommand{CommandID: "command:medic-attack", PlayerID: 2, RequestID: 2,
		UnitIDs: []string{medic.ID}, Verb: "unit.attack", TargetID: identity.ID}
	s.parkMessage(nil, world.Message("combat.command", "session-a", "park:medic-attack", "openrct2", 1, command))
	if len(s.commands) != 0 {
		t.Fatal("Medic attack command was forwarded")
	}
	command.CommandID, command.Verb, command.RequestID = "command:medic-heal", "unit.heal", 3
	forwarded = make(chan world.Envelope, 1)
	go func() {
		var message world.Envelope
		_ = json.Unmarshal([]byte(readLine(controllerSide)), &message)
		forwarded <- message
	}()
	s.parkMessage(nil, world.Message("combat.command", "session-a", "park:medic-heal", "openrct2", 1, command))
	var heal worldCommand
	if message := <-forwarded; message.Kind != "combat.command" || message.Decode(&heal) != nil ||
		heal.TargetProxyID != identity.ID || len(s.commands) != 1 {
		t.Fatalf("Medic heal command was not forwarded to its confirmed target: %+v", message)
	}
	delete(s.commands, command.CommandID)
	command.CommandID, command.RequestID, command.TargetID = "command:medic-static-heal", 4, "openbw:1000"
	forwarded = make(chan world.Envelope, 1)
	go func() {
		var message world.Envelope
		_ = json.Unmarshal([]byte(readLine(controllerSide)), &message)
		forwarded <- message
	}()
	s.parkMessage(nil, world.Message("combat.command", "session-a", "park:medic-static-heal", "openrct2", 1, command))
	if message := <-forwarded; message.Decode(&heal) != nil || heal.TargetProxyID != "openbw:1000" {
		t.Fatalf("Medic could not heal a static Marine: %+v", message)
	}
	delete(s.commands, command.CommandID)
	if err := s.actors.Despawn(world.ActorDespawn{ID: identity.ID, Session: identity.Session, Generation: 1}); err != nil {
		t.Fatal(err)
	}
	request("command:removed")
	if len(s.commands) != 0 {
		t.Fatal("removed actor command was forwarded")
	}
}

func TestOffParkActorDoesNotInvalidateCombatSnapshot(t *testing.T) {
	s := testService()
	if err := s.registry.Replace("session-a", 1, 64, 64, nil, nil); err != nil {
		t.Fatal(err)
	}
	s.transform, _ = world.Fit(64, 64, 128, 128)
	s.ready = true
	bridgeSide, parkSide := net.Pipe()
	defer bridgeSide.Close()
	defer parkSide.Close()
	s.park = &peer{Conn: bridgeSide}
	forwarded := make(chan world.Envelope, 1)
	go func() {
		var message world.Envelope
		_ = json.Unmarshal([]byte(readLine(parkSide)), &message)
		forwarded <- message
	}()
	s.bwMessage(nil, world.Message("combat.snapshot", "session-a", "bw:snapshot", "openbw", 1,
		map[string]any{"seq": 1, "bw_tick": 3, "unit_total": 2, "unit_omitted": 0,
			"units": []map[string]any{
				{"id": "openbw:1000", "x": 1040, "y": 1040},
				{"id": "openbw:3001", "x": 592, "y": 976},
			}}))
	var snapshot struct {
		UnitOmitted int              `json:"unit_omitted"`
		Units       []map[string]any `json:"units"`
	}
	message := <-forwarded
	if message.Kind != "combat.snapshot" || message.Decode(&snapshot) != nil ||
		len(snapshot.Units) != 1 || snapshot.UnitOmitted != 1 ||
		snapshot.Units[0]["x"] != float64(16) {
		t.Fatalf("off-park actor invalidated snapshot: %+v", snapshot)
	}
}

func TestWorldCommandResolvesLogicalTargetAndCorrelatesResult(t *testing.T) {
	s := testService()
	e := testEntity()
	if err := s.registry.Replace("session-a", 1, 8, 8, []world.Entity{e}, nil); err != nil {
		t.Fatal(err)
	}
	s.ready = true
	s.proxies[e.ID] = "openbw:7"
	first, second := net.Pipe()
	defer first.Close()
	defer second.Close()
	s.controller = &peer{Conn: first}
	got := make(chan world.Envelope, 1)
	go func() {
		var message world.Envelope
		_ = json.Unmarshal([]byte(readLine(second)), &message)
		got <- message
	}()
	command := worldCommand{CommandID: "session-a:1", PlayerID: 2, RequestID: 9,
		UnitIDs: []string{"openbw:10"}, Verb: "unit.attack", TargetID: e.ID}
	s.parkMessage(nil, world.Message("combat.command", "session-a", "park:order", "openrct2", 1, command))
	forwarded := <-got
	if forwarded.Kind != "combat.command" || forwarded.Session != "session-a" {
		t.Fatal("command was not forwarded")
	}
	var resolved worldCommand
	if err := forwarded.Decode(&resolved); err != nil || resolved.TargetProxyID != "openbw:7" {
		t.Fatalf("logical target was not resolved: %+v, %v", resolved, err)
	}
	parkSide, bridgeSide := net.Pipe()
	defer parkSide.Close()
	defer bridgeSide.Close()
	s.park = &peer{Conn: parkSide}
	result := make(chan world.Envelope, 1)
	go func() {
		var message world.Envelope
		_ = json.Unmarshal([]byte(readLine(bridgeSide)), &message)
		result <- message
	}()
	s.controllerMessage(nil, world.Message("combat.result", "session-a", "controller:result", "openbw", 1,
		map[string]any{"command_id": command.CommandID, "player_id": command.PlayerID,
			"request_id": command.RequestID, "accepted": true, "reason": "ok"}))
	if answer := <-result; answer.Kind != "combat.result" || s.commands[command.CommandID].CommandID != "" {
		t.Fatal("command result was not correlated and forwarded")
	}
}

func TestGeneralizedTrainingCommand(t *testing.T) {
	s := testService()
	e := testEntity()
	e.ID, e.SourceID, e.Kind, e.Type, e.Owner = "openrct2:large_scenery:3:1:1#1", "large_scenery:3:1:1", "structure", "terran_barracks", 1
	e.Geometry.Rects = []world.Rect{{X: 32, Y: 32, Width: 128, Height: 96}}
	e.Combat.Health = 1000
	if err := s.registry.Replace("session-a", 1, 8, 8, []world.Entity{e}, nil); err != nil {
		t.Fatal(err)
	}
	s.ready = true
	s.proxies[e.ID] = "openbw:77"
	bridge, native := net.Pipe()
	defer bridge.Close()
	defer native.Close()
	s.controller = &peer{Conn: bridge}
	forwarded := make(chan world.Envelope, 1)
	go func() { var m world.Envelope; _ = json.Unmarshal([]byte(readLine(native)), &m); forwarded <- m }()
	command := worldCommand{CommandID: "session-a:1", PlayerID: 2, RequestID: 1, Verb: "unit.train", TargetID: e.ID, UnitIDs: []string{}}
	s.parkMessage(nil, world.Message("combat.command", "session-a", "park:train:1", "openrct2", 1, command))
	var actual worldCommand
	if err := (<-forwarded).Decode(&actual); err != nil || actual.UnitType != "terran_marine" || actual.TargetProxyID != "openbw:77" {
		t.Fatalf("legacy train default: %+v %v", actual, err)
	}
	s.parkMessage(nil, world.Message("combat.command", "session-a", "park:train:retry", "openrct2", 1, command))
	if len(s.commands) != 1 {
		t.Fatal("duplicate training command forwarded")
	}
	command.CommandID, command.RequestID, command.UnitType = "session-a:2", 2, "terran_ghost"
	s.parkMessage(nil, world.Message("combat.command", "session-a", "park:train:unsupported", "openrct2", 1, command))
	if len(s.commands) != 1 {
		t.Fatal("unsupported unit forwarded")
	}
	s.parkMessage(nil, world.Message("combat.command", "session-a", "park:train:empty", "openrct2", 1,
		map[string]any{"command_id": "session-a:empty", "player_id": 2, "request_id": 4,
			"unit_ids": []string{}, "verb": "unit.train", "unit_type": "", "target_id": e.ID}))
	if len(s.commands) != 1 {
		t.Fatal("explicit empty unit type used legacy default")
	}
	command.CommandID, command.RequestID, command.UnitType = "session-a:3", 3, "zerg_zergling"
	s.parkMessage(nil, world.Message("combat.command", "session-a", "park:train:wrong-producer", "openrct2", 1, command))
	if len(s.commands) != 1 {
		t.Fatal("inappropriate production forwarded")
	}
}

func TestZergProductionRequiresScenarioAuthorityAndRoutesToOwner(t *testing.T) {
	s := testService()
	e := testEntity()
	e.ID, e.SourceID, e.Kind, e.Type, e.Owner = "openrct2:large_scenery:7:1:1#1", "large_scenery:7:1:1", "structure", "zerg_hatchery", 0
	e.Geometry.Rects = []world.Rect{{X: 32, Y: 32, Width: 128, Height: 96}}
	e.Combat.Health = 1250
	if err := s.registry.Replace("session-a", 1, 8, 8, []world.Entity{e}, nil); err != nil {
		t.Fatal(err)
	}
	s.ready = true
	s.proxies[e.ID] = "openbw:77"
	s.controller = &peer{}
	command := worldCommand{CommandID: "session-a:1", PlayerID: 2, RequestID: 1,
		Verb: "unit.train", UnitType: "zerg_zergling", TargetID: e.ID, UnitIDs: []string{}}
	s.parkMessage(nil, world.Message("combat.command", "session-a", "park:zerg:denied", "openrct2", 1, command))
	if len(s.commands) != 0 {
		t.Fatal("enemy Hatchery accepted without scenario command authority")
	}
	s.scenario = &world.Scenario{ProductionControlOwners: []int{0}}
	bridge, native := net.Pipe()
	defer bridge.Close()
	defer native.Close()
	s.bw = &peer{Conn: bridge}
	forwarded := make(chan world.Envelope, 1)
	go func() {
		var m world.Envelope
		_ = json.Unmarshal([]byte(readLine(native)), &m)
		forwarded <- m
	}()
	s.parkMessage(nil, world.Message("combat.command", "session-a", "park:zerg:allowed", "openrct2", 1, command))
	select {
	case message := <-forwarded:
		var actual worldCommand
		if message.Kind != "combat.command" || message.Decode(&actual) != nil ||
			actual.UnitType != "zerg_zergling" || actual.TargetProxyID != "openbw:77" {
			t.Fatalf("Zerg command was not routed to native owner: %+v", message)
		}
	case <-time.After(time.Second):
		t.Fatal("authorized Zerg command was not forwarded")
	}
}

func TestAcademyBuildingStateWithoutProduction(t *testing.T) {
	s := testService()
	e := testEntity()
	e.ID, e.SourceID, e.Kind, e.Type, e.Owner = "openrct2:large_scenery:4:1:1#1", "large_scenery:4:1:1", "structure", "terran_academy", 1
	e.Geometry.Rects = []world.Rect{{X: 32, Y: 32, Width: 96, Height: 64}}
	e.Combat.Health = 600
	if err := s.registry.Replace("session-a", 1, 8, 8, []world.Entity{e}, nil); err != nil {
		t.Fatal(err)
	}
	s.proxies[e.ID] = "openbw:77"
	bridge, park := net.Pipe()
	defer bridge.Close()
	defer park.Close()
	s.park = &peer{Conn: bridge}
	forwarded := make(chan world.Envelope, 1)
	go func() {
		var message world.Envelope
		_ = json.Unmarshal([]byte(readLine(park)), &message)
		forwarded <- message
	}()
	s.controllerMessage(nil, world.Message("building.state", "session-a", "controller:academy", "openbw", 1,
		map[string]any{"id": e.ID, "native_id": "openbw:77", "owner": 1,
			"race": "Terran", "completed": true, "commands": []any{},
			"health": 600, "max_health": 600, "queue": 0, "remaining_frames": 0,
			"minerals": 500, "gas": 250, "supply_used": 10, "supply_total": 16}))
	select {
	case message := <-forwarded:
		if message.Kind != "building.state" {
			t.Fatalf("academy state was not forwarded: %+v", message)
		}
		var state map[string]any
		if message.Decode(&state) != nil || state["larva_count"] != nil {
			t.Fatalf("academy acquired a fabricated larva count: %+v", state)
		}
	case <-time.After(time.Second):
		t.Fatal("academy state was not forwarded")
	}
}

func TestHatcheryNativeMorphStatusSurvivesBridge(t *testing.T) {
	s := testService()
	e := testEntity()
	e.ID, e.SourceID, e.Kind, e.Type, e.Owner = "openrct2:large_scenery:7:1:1#1", "large_scenery:7:1:1", "structure", "zerg_hatchery", 0
	e.Geometry.Rects = []world.Rect{{X: 32, Y: 32, Width: 128, Height: 96}}
	e.Combat.Health = 1250
	if err := s.registry.Replace("session-a", 1, 8, 8, []world.Entity{e}, nil); err != nil {
		t.Fatal(err)
	}
	s.proxies[e.ID] = "openbw:77"
	bridge, park := net.Pipe()
	defer bridge.Close()
	defer park.Close()
	s.park = &peer{Conn: bridge}
	forwarded := make(chan world.Envelope, 1)
	go func() {
		var message world.Envelope
		_ = json.Unmarshal([]byte(readLine(park)), &message)
		forwarded <- message
	}()
	s.controllerMessage(nil, world.Message("building.state", "session-a", "publisher:hatchery", "openbw", 1,
		map[string]any{"id": e.ID, "native_id": "openbw:77", "owner": 0,
			"race": "Zerg", "completed": true, "health": 1250, "max_health": 1250,
			"queue": 0, "remaining_frames": 0, "minerals": 450, "gas": 0,
			"supply_used": 1, "supply_total": 18, "larva_count": 2,
			"morph_count": 1, "morph_remaining_frames": 372,
			"availability": map[string]any{"zerg_zergling": map[string]any{
				"ready": true, "reason": "ready", "requirement": ""}},
			"commands": []any{map[string]any{"slot": 0, "action": "unit.train",
				"unit_type": "zerg_zergling", "label": "Zerg Zergling",
				"ready": true, "reason": "ready", "requirement": ""}}}))
	select {
	case message := <-forwarded:
		var state map[string]any
		if message.Decode(&state) != nil || state["larva_count"] != float64(2) ||
			state["morph_count"] != float64(1) || state["morph_remaining_frames"] != float64(372) ||
			state["command_authorized"] != false {
			t.Fatalf("native morph status was changed or authorized by the bridge: %+v", state)
		}
	case <-time.After(time.Second):
		t.Fatal("hatchery state was not forwarded")
	}
}

func TestPlayerResourcesRequireNativeGas(t *testing.T) {
	s := testService()
	if err := s.registry.Replace("session-a", 1, 8, 8, nil, nil); err != nil {
		t.Fatal(err)
	}
	bridge, park := net.Pipe()
	defer bridge.Close()
	defer park.Close()
	s.park = &peer{Conn: bridge}
	forwarded := make(chan world.Envelope, 1)
	go func() {
		var message world.Envelope
		_ = json.Unmarshal([]byte(readLine(park)), &message)
		forwarded <- message
	}()
	message := map[string]any{"owner": 1, "minerals": 500,
		"supply_used": 10, "supply_total": 16}
	s.controllerMessage(nil, world.Message("player.resources", "session-a", "controller:missing-gas", "openbw", 1, message))
	message["gas"] = 250
	s.controllerMessage(nil, world.Message("player.resources", "session-a", "controller:with-gas", "openbw", 1, message))
	select {
	case actual := <-forwarded:
		var report struct {
			Gas *int `json:"gas"`
		}
		if actual.Kind != "player.resources" || actual.Decode(&report) != nil ||
			report.Gas == nil || *report.Gas != 250 {
			t.Fatalf("accepted missing gas resource report: %+v", actual)
		}
	case <-time.After(time.Second):
		t.Fatal("valid native resource report was not forwarded")
	}
}

func TestTargetLinkIsForwardedAndValidated(t *testing.T) {
	s := testService()
	e := testEntity()
	if err := s.registry.Replace("session-a", 3, 8, 8, []world.Entity{e}, nil); err != nil {
		t.Fatal(err)
	}
	s.bwWidth, s.bwHeight = 128, 128
	s.transform, _ = world.Fit(8, 8, 128, 128)
	var navErr error
	s.navigationMask, navErr = world.DeriveNavigation(s.registry, s.transform, 128, 128)
	if navErr != nil {
		t.Fatal(navErr)
	}
	s.navigationRevision = 3
	bridgeSide, controllerSide := net.Pipe()
	defer bridgeSide.Close()
	defer controllerSide.Close()
	s.controller = &peer{Conn: bridgeSide}
	got := make(chan world.Envelope, 1)
	go func() {
		var forwarded world.Envelope
		_ = json.Unmarshal([]byte(readLine(controllerSide)), &forwarded)
		got <- forwarded
	}()
	link := targetLink{ID: e.ID, ProxyID: "openbw:19", X: 250, Y: 300}
	s.bwMessage(nil, world.Message("entity.state", "session-a", "bw:link", "openbw", 3, link))
	forwarded := <-got
	if forwarded.Kind != "entity.state" || s.targetLinks[e.ID] != link {
		t.Fatalf("target link was not forwarded and retained: %+v", forwarded)
	}
	s.bwMessage(nil, world.Message("world.ready", "session-a", "bw:ready", "openbw", 3,
		world.Ready{Entities: 1, Targets: 1}))
	if s.ready || s.pendingReady == nil {
		t.Fatal("world was announced ready before the controller acknowledged its target link")
	}
	s.controllerMessage(nil, world.Message("world.ack", "session-a", "controller:ack", "openbw", 3,
		world.Ack{OpID: forwarded.OpID, Accepted: true}))
	if s.ready {
		t.Fatal("target acknowledgement bypassed controller navigation")
	}
	s.controllerMessage(nil, world.Message("navigation.mask.applied", "session-a", "controller:navigation", "openbw", 3,
		map[string]any{"hash": s.navigationMask.Hash, "accepted": true}))
	if s.ready {
		t.Fatal("controller alone released world readiness")
	}
	s.bwMessage(nil, world.Message("navigation.mask.applied", "session-a", "publisher:navigation", "openbw", 3,
		map[string]any{"hash": s.navigationMask.Hash, "accepted": true}))
	if !s.ready || s.pendingReady != nil {
		t.Fatal("acknowledged target link did not release world readiness")
	}
	s.bwMessage(nil, world.Message("entity.state", "stale-session", "bw:stale", "openbw", 3,
		targetLink{ID: e.ID, ProxyID: "openbw:20", X: 250, Y: 300}))
	if s.targetLinks[e.ID].ProxyID != "openbw:19" {
		t.Fatal("stale target link replaced the authoritative mapping")
	}
}

func TestNativeTargetHealthUpdateReachesPark(t *testing.T) {
	s := testService()
	e := testEntity()
	if err := s.registry.Replace("session-a", 3, 8, 8, []world.Entity{e}, nil); err != nil {
		t.Fatal(err)
	}
	s.bwWidth, s.bwHeight = 128, 128
	s.lastReady = &world.Ready{Entities: 1, Targets: 1}
	s.proxies = map[string]string{}
	s.targetLinks = map[string]targetLink{}
	s.proxies[e.ID] = "openbw:19"
	s.targetLinks[e.ID] = targetLink{ID: e.ID, ProxyID: "openbw:19", X: 250, Y: 300, Health: 40}
	bridgeSide, parkSide := net.Pipe()
	defer bridgeSide.Close()
	defer parkSide.Close()
	s.park = &peer{Conn: bridgeSide}
	done := make(chan struct{})
	go func() {
		s.bwMessage(nil, world.Message("entity.state", "session-a", "bw:health", "openbw", 3,
			targetLink{ID: e.ID, ProxyID: "openbw:19", X: 250, Y: 300, Health: 23}))
		close(done)
	}()
	var update world.Envelope
	if err := json.Unmarshal([]byte(readLine(parkSide)), &update); err != nil {
		t.Fatal(err)
	}
	<-done
	var link targetLink
	if update.Kind != "entity.target" || update.Decode(&link) != nil || link.Health != 23 {
		t.Fatalf("native health update was not published to the park: %+v", update)
	}
}

func readLine(connection net.Conn) string {
	line, _ := bufio.NewReader(connection).ReadString('\n')
	return line
}
func testEntity() world.Entity {
	return world.Entity{ID: "openrct2:ride:1#1", Source: "openrct2", SourceID: "ride:1", Kind: "ride", Type: "carousel", Position: world.Point{X: 48, Y: 48}, Geometry: world.Geometry{Cells: []world.Point{{X: 1, Y: 1}}, Rects: []world.Rect{{X: 32, Y: 32, Width: 32, Height: 32}}}, Destructible: true, Combat: world.Combat{Targetable: true, Health: 100}, Revision: 1, Removal: world.Removal{Action: "ridedemolish", Args: map[string]int{"ride": 1}}}
}
func TestSnapshotOrderingAndCombatConfirmation(t *testing.T) {
	s := testService()
	sid := "session-a"
	s.parkMessage(nil, world.Message("world.snapshot.begin", sid, "park:1", "openrct2", 1, world.SnapshotBegin{Width: 8, Height: 8, Chunks: 2}))
	e := testEntity()
	chunk := world.Message("world.snapshot.chunk", sid, "park:2", "openrct2", 1, world.SnapshotChunk{Index: 0, Entities: []world.Entity{e}})
	s.parkMessage(nil, chunk)
	s.parkMessage(nil, chunk) // Duplicate operation cannot append the same entity twice.
	if s.stage.chunks != 1 || len(s.stage.entities) != 1 {
		t.Fatal("duplicate snapshot chunk applied")
	}
	s.parkMessage(nil, world.Message("world.snapshot.chunk", sid, "park:3", "openrct2", 1, world.SnapshotChunk{Index: 2, Terrain: []world.Terrain{{X: 0, Y: 0}}}))
	if s.stage.chunks != 1 {
		t.Fatal("out of order chunk applied")
	}
	s.parkMessage(nil, world.Message("world.snapshot.chunk", sid, "park:4", "openrct2", 1, world.SnapshotChunk{Index: 1, Terrain: []world.Terrain{{X: 0, Y: 0}}}))
	s.parkMessage(nil, world.Message("world.snapshot.end", sid, "park:5", "openrct2", 1, world.SnapshotEnd{Entities: 1, Terrain: 1}))
	if s.registry.Entities[e.ID].ID == "" || s.registry.Revision != 1 {
		t.Fatal("complete snapshot not committed")
	}
	s.proxies[e.ID] = "openbw:7"
	s.ready = true
	event := world.CombatEvent{ID: "death:1", EntityID: e.ID, ProxyID: "openbw:7", Type: "destruction", Health: 0}
	s.bwMessage(nil, world.Message("combat.event", sid, "bw:1", "openbw", 1, event))
	if s.registry.Destroyed[e.ID] || s.pending[event.ID].ID == "" || s.registry.RemovalState[e.ID] != "destruction_requested" {
		t.Fatal("OpenBW death prematurely confirmed park removal")
	}
	s.parkMessage(nil, world.Message("combat.result", sid, "park:6", "openrct2", 1, world.CombatResult{EventID: event.ID, EntityID: e.ID, State: "removal_failed"}))
	if s.registry.Destroyed[e.ID] || s.registry.Revision != 1 || s.registry.RemovalState[e.ID] != "removal_failed" {
		t.Fatal("failed removal changed world state")
	}
	// A failed native removal requires an authoritative resync and a fresh
	// proxy generation before another death may request demolition.
	s.parkMessage(nil, world.Message("world.snapshot.begin", sid, "park:resync", "openrct2", 1, world.SnapshotBegin{Width: 8, Height: 8, Chunks: 1}))
	s.parkMessage(nil, world.Message("world.snapshot.chunk", sid, "park:resync-chunk", "openrct2", 1, world.SnapshotChunk{Index: 0, Entities: []world.Entity{e}}))
	s.parkMessage(nil, world.Message("world.snapshot.end", sid, "park:resync-end", "openrct2", 1, world.SnapshotEnd{Entities: 1}))
	s.proxies[e.ID] = "openbw:8"
	s.ready = true
	transform, err := world.Fit(8, 8, 8, 8)
	if err != nil {
		t.Fatal(err)
	}
	s.transform, s.bwWidth, s.bwHeight = transform, 8, 8
	s.navigationMask, err = world.DeriveNavigation(s.registry, transform, 8, 8)
	if err != nil {
		t.Fatal(err)
	}
	event.ID = "death:2"
	event.ProxyID = "openbw:8"
	s.ready = false // Reconnected publisher may report the old zero-HP target before readiness.
	s.bwMessage(nil, world.Message("combat.event", sid, "bw:2", "openbw", 1, event))
	if s.pending[event.ID].ID == "" {
		t.Fatal("replayed native destruction was lost during reconciliation")
	}
	s.parkMessage(nil, world.Message("combat.result", sid, "park:7", "openrct2", 2, world.CombatResult{EventID: event.ID, EntityID: e.ID, State: "removal_confirmed"}))
	if s.registry.Destroyed[e.ID] || s.registry.Revision != 1 || s.parkPatch == nil {
		t.Fatal("confirmed park removal committed before native application")
	}
	hash := s.parkPatch.mask.Hash
	for _, participant := range []string{"publisher", "controller"} {
		s.nativePatchReport(participant, world.Message("navigation.mask.staged", sid, participant+":stage", "openbw", 2,
			map[string]any{"hash": hash, "accepted": true}))
	}
	frame := s.parkPatch.applyFrame
	for _, participant := range []string{"publisher", "controller"} {
		s.nativePatchReport(participant, world.Message("navigation.mask.scheduled", sid, participant+":schedule", "openbw", 2,
			map[string]any{"hash": hash, "accepted": true, "apply_frame": frame}))
	}
	for _, participant := range []string{"publisher", "controller"} {
		applied := world.Message("navigation.mask.applied", sid, participant+":applied", "openbw", 2,
			map[string]any{"hash": hash, "accepted": true})
		applied.BWTick = frame
		s.nativePatchReport(participant, applied)
	}
	if !s.registry.Destroyed[e.ID] || s.registry.Revision != 2 || s.registry.RemovalState[e.ID] != "removal_confirmed" {
		t.Fatal("confirmed removal not recorded")
	}
}

func TestLiveUpdateIsExplicitlyRejected(t *testing.T) {
	s := testService()
	e := testEntity()
	if err := s.registry.Replace("session-a", 1, 8, 8, []world.Entity{e}, nil); err != nil {
		t.Fatal(err)
	}
	changed := e
	changed.Revision = 2
	changed.Position.X = 96
	s.parkMessage(nil, world.Message("entity.upsert", "session-a", "park:update", "openrct2", 2, changed))
	if s.registry.Revision != 1 || s.registry.Entities[e.ID].Position.X != 48 {
		t.Fatal("unsupported live update changed authoritative registry")
	}
}

func TestSnapshotRejectsStaleRevisionAndRetiredSession(t *testing.T) {
	s := testService()
	if err := s.registry.Replace("session-a", 3, 8, 8, []world.Entity{testEntity()}, nil); err != nil {
		t.Fatal(err)
	}
	begin := world.SnapshotBegin{Width: 8, Height: 8, Chunks: 1}
	s.parkMessage(nil, world.Message("world.snapshot.begin", "session-a", "park:old", "openrct2", 2, begin))
	if s.stage != nil {
		t.Fatal("stale revision staged")
	}
	s.parkMessage(nil, world.Message("world.snapshot.begin", "session-b", "park:new", "openrct2", 1, begin))
	s.parkMessage(nil, world.Message("world.snapshot.chunk", "session-b", "park:chunk", "openrct2", 1, world.SnapshotChunk{Index: 0}))
	s.parkMessage(nil, world.Message("world.snapshot.end", "session-b", "park:end", "openrct2", 1, world.SnapshotEnd{}))
	if s.registry.Session != "session-b" || !s.retired["session-a"] {
		t.Fatal("new session did not retire prior session")
	}
	s.parkMessage(nil, world.Message("world.snapshot.begin", "session-a", "park:replay", "openrct2", 4, begin))
	if s.stage != nil {
		t.Fatal("retired session staged")
	}
}
