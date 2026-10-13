package world

import "testing"

func testActor() ActorIdentity {
	return ActorIdentity{ID: "openbw:3001", Engine: "openbw", Type: "terran_marine", Owner: 1,
		Generation: 17, Session: "park-session"}
}

func TestActorLifecycleAndNativeBindings(t *testing.T) {
	identity := testActor()
	actors := NewActorRegistry(identity.Session)
	if err := actors.Spawn(identity); err != nil {
		t.Fatal(err)
	}
	if err := actors.Spawn(identity); err != nil {
		t.Fatalf("repeated spawn: %v", err)
	}
	if actors.Commandable(identity.ID) {
		t.Fatal("unbound actor became commandable")
	}
	publisher := ActorBinding{ID: identity.ID, Session: identity.Session, Generation: identity.Generation,
		Participant: "publisher", NativeID: "12"}
	controller := publisher
	controller.Participant, controller.NativeID = "controller", "208"
	if err := actors.Bind(publisher); err != nil {
		t.Fatal(err)
	}
	if actors.Commandable(identity.ID) {
		t.Fatal("single binding became commandable")
	}
	if err := actors.Bind(controller); err != nil {
		t.Fatal(err)
	}
	if !actors.Commandable(identity.ID) {
		t.Fatal("both bindings did not activate actor")
	}
	if err := actors.Bind(controller); err != nil {
		t.Fatalf("repeated binding: %v", err)
	}
	changed := controller
	changed.NativeID = "209"
	if err := actors.Bind(changed); err == nil {
		t.Fatal("conflicting native binding accepted")
	}
	other := identity
	other.ID = "openbw:3002"
	if err := actors.Spawn(other); err != nil {
		t.Fatal(err)
	}
	collision := publisher
	collision.ID = other.ID
	if err := actors.Bind(collision); err == nil {
		t.Fatal("native ID collision accepted")
	}
	if err := actors.Despawn(ActorDespawn{ID: identity.ID, Session: identity.Session,
		Generation: identity.Generation}); err != nil {
		t.Fatal(err)
	}
	if actors.Commandable(identity.ID) {
		t.Fatal("despawn left actor commandable")
	}
	if record, _ := actors.Lookup(identity.ID); len(record.Bindings) != 0 {
		t.Fatal("despawn retained bindings")
	}
	if err := actors.Spawn(identity); err == nil {
		t.Fatal("ID reused after despawn")
	}
	if err := actors.Bind(controller); err == nil {
		t.Fatal("despawned binding accepted")
	}
	if err := actors.Despawn(ActorDespawn{ID: identity.ID, Session: identity.Session,
		Generation: identity.Generation}); err != nil {
		t.Fatalf("repeated despawn: %v", err)
	}
}

func TestActorReconciliationAndSessionIsolation(t *testing.T) {
	identity := testActor()
	actors := NewActorRegistry(identity.Session)
	if err := actors.Reconcile(identity.Session, []ActorIdentity{identity}); err != nil {
		t.Fatal(err)
	}
	if err := actors.Reconcile(identity.Session, []ActorIdentity{identity, identity}); err == nil {
		t.Fatal("duplicate reconciliation accepted")
	}
	if err := actors.Reconcile("old-session", nil); err == nil {
		t.Fatal("stale session accepted")
	}
	binding := ActorBinding{ID: identity.ID, Session: identity.Session, Generation: identity.Generation,
		Participant: "publisher", NativeID: "12"}
	if err := actors.Bind(binding); err != nil {
		t.Fatal(err)
	}
	if err := actors.Reconcile(identity.Session, []ActorIdentity{identity}); err != nil {
		t.Fatal(err)
	}
	if record, _ := actors.Lookup(identity.ID); len(record.Bindings) != 1 {
		t.Fatal("reconcile lost living binding")
	}
	if err := actors.Reconcile(identity.Session, nil); err != nil {
		t.Fatal(err)
	}
	if record, _ := actors.Lookup(identity.ID); record.State != ActorRemoved {
		t.Fatal("absent actor survived reconciliation")
	}
	if err := actors.Reset("new-session"); err != nil {
		t.Fatal(err)
	}
	identity.Session = "new-session"
	if err := actors.Spawn(identity); err != nil {
		t.Fatal(err)
	}
	if err := actors.Bind(binding); err == nil {
		t.Fatal("old session binding accepted")
	}
}

func TestActorEnvelopeValidation(t *testing.T) {
	identity := testActor()
	valid := Message("actor.spawn", identity.Session, "bw:1", "openbw", 1, identity)
	if err := valid.Validate(); err != nil {
		t.Fatal(err)
	}
	valid.Source = "openrct2"
	if err := valid.Validate(); err == nil {
		t.Fatal("wrong actor authority accepted")
	}
	invalid := Message("actor.spawn", identity.Session, "bw:2", "openbw", 1,
		map[string]any{"id": identity.ID, "engine": "openbw", "type": identity.Type,
			"owner": 1, "generation": 17, "session": "other-session"})
	if err := invalid.Validate(); err == nil {
		t.Fatal("payload session mismatch accepted")
	}
	stale := Message("actor.bind", identity.Session, "bw:3", "openbw", 1,
		ActorBinding{ID: identity.ID, Session: identity.Session, Generation: 0,
			Participant: "controller", NativeID: "18"})
	if err := stale.Validate(); err == nil {
		t.Fatal("missing generation accepted")
	}
}
