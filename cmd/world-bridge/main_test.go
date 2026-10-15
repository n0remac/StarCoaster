package main

import (
	"bufio"
	"encoding/json"
	"net"
	"testing"
	"time"

	"starcoaster/internal/world"
)

func testService() *service {
	return &service{registry: world.NewRegistry(), mapping: world.DefaultMapping(), pending: map[string]world.CombatEvent{}, proxies: map[string]string{}}
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
	event.ID = "death:2"
	event.ProxyID = "openbw:8"
	s.bwMessage(nil, world.Message("combat.event", sid, "bw:2", "openbw", 1, event))
	s.parkMessage(nil, world.Message("combat.result", sid, "park:7", "openrct2", 2, world.CombatResult{EventID: event.ID, EntityID: e.ID, State: "removal_confirmed"}))
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
