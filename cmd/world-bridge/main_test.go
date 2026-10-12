package main

import (
	"testing"

	"starcoaster/internal/world"
)

func testService() *service {
	return &service{registry: world.NewRegistry(), mapping: world.DefaultMapping(), pending: map[string]world.CombatEvent{}, proxies: map[string]string{}}
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
