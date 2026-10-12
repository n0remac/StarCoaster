package main

import (
	"bufio"
	"encoding/json"
	"net"
	"testing"

	"starcoaster/internal/world"
)

func testService() *service {
	return &service{registry: world.NewRegistry(), mapping: world.DefaultMapping(), pending: map[string]world.CombatEvent{}, proxies: map[string]string{}}
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
