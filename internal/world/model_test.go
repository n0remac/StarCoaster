package world

import "testing"

func exampleEntity(id string) Entity {
	return Entity{ID: id, Source: "openrct2", SourceID: "ride:17", Kind: "ride", Type: "rct2.ride.mgr1",
		Position: Point{64, 96}, Elevation: 112, Geometry: Geometry{Cells: []Point{{2, 3}, {3, 3}},
			Rects: []Rect{{64, 96, 64, 32}}}, Destructible: true, Combat: Combat{Targetable: true, Health: 400}, Revision: 1}
}
func TestSnapshotAtomicAndIdentity(t *testing.T) {
	r := NewRegistry()
	original := exampleEntity("openrct2:ride:17#1")
	if err := r.Replace("session-a", 1, 8, 8, []Entity{original}, []Terrain{{X: 2, Y: 3}}); err != nil {
		t.Fatal(err)
	}
	bad := exampleEntity("openrct2:ride:17#2")
	bad.Geometry.Rects[0].X = 255
	if err := r.Replace("session-b", 1, 8, 8, []Entity{bad}, nil); err == nil {
		t.Fatal("accepted out of bounds geometry")
	}
	if r.Session != "session-a" || len(r.Entities) != 1 {
		t.Fatal("failed snapshot changed live registry")
	}
	bad = exampleEntity("openrct2:ride:17#2")
	if err := r.Replace("session-b", 1, 8, 8, []Entity{bad}, nil); err != nil {
		t.Fatal(err)
	}
	if r.Entities[original.ID].ID != "" || r.Entities[bad.ID].ID == "" {
		t.Fatal("rebuilt object reused old identity")
	}
}
func TestRevisionAndDuplicateOperations(t *testing.T) {
	r := NewRegistry()
	e := exampleEntity("openrct2:ride:17#1")
	if err := r.Replace("session-a", 1, 8, 8, []Entity{e}, nil); err != nil {
		t.Fatal(err)
	}
	m := Message("entity.remove", "session-a", "park:remove-1", "openrct2", 3, map[string]string{"id": e.ID})
	if a := r.Apply(m); a.Accepted || a.Error != "out_of_order_revision" {
		t.Fatalf("out of order: %+v", a)
	}
	m.OpID = "park:remove-2"
	m.Revision = 2
	if a := r.Apply(m); !a.Accepted {
		t.Fatalf("valid remove: %+v", a)
	}
	if a := r.Apply(m); !a.Accepted || r.Revision != 2 {
		t.Fatalf("duplicate changed revision: %+v", a)
	}
	m.OpID = "park:remove-3"
	m.Revision = 3
	if a := r.Apply(m); a.Accepted || a.Error != "unknown_entity" {
		t.Fatalf("second remove: %+v", a)
	}
}
func TestMappingDefaultsAndOverrides(t *testing.T) {
	m := DefaultMapping()
	e := m.Apply(exampleEntity("openrct2:ride:17#1"))
	if !e.Destructible || !e.Combat.Targetable || !e.Collision.Blocks || e.Combat.Health != 400 {
		t.Fatalf("ride defaults: %+v", e)
	}
	falseValue := false
	damageScale := 0.75
	m.Rules = append(m.Rules, Rule{Kind: "ride", Type: e.Type, Destructible: &falseValue, DamageScale: &damageScale, Effect: "collapse"})
	e = m.Apply(e)
	if e.Destructible || e.Combat.Targetable || e.Combat.DamageScale != 0.75 || e.Removal.Effect != "collapse" {
		t.Fatal("override failed")
	}
	terrain := m.Apply(Entity{Kind: "terrain", Destructible: true})
	if terrain.Destructible || terrain.Combat.Targetable {
		t.Fatal("terrain became destructible")
	}
}

func TestOpenBWEntityCanUseUnifiedModelButNotParkAuthority(t *testing.T) {
	e := exampleEntity("openbw:unit:7")
	e.Source = "openbw"
	e.SourceID = "7"
	e.Kind = "unit"
	e.Type = "zerg_zergling"
	e.Geometry = Geometry{}
	e.Destructible = false
	if err := e.Validate(8, 8); err != nil {
		t.Fatal(err)
	}
	if err := NewRegistry().Replace("session-a", 1, 8, 8, []Entity{e}, nil); err == nil {
		t.Fatal("accepted OpenBW entity in authoritative park snapshot")
	}
}
