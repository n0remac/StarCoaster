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
	publisher.CreationFrame = 153
	controller.CreationFrame = 154
	if err := actors.Bind(publisher); err != nil {
		t.Fatal(err)
	}
	if actors.Commandable(identity.ID) {
		t.Fatal("single binding became commandable")
	}
	if err := actors.Bind(controller); err == nil {
		t.Fatal("mismatched synchronized creation frame accepted")
	}
	controller.CreationFrame = publisher.CreationFrame
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

func TestNativeMorphKeepsCanonicalIDAndBindings(t *testing.T) {
	identity := ActorIdentity{ID: "openbw:3001", Engine: "openbw", Type: "zerg_larva",
		Owner: 0, Phase: "complete", Generation: 17, Session: "park-session"}
	actors := NewActorRegistry(identity.Session)
	if err := actors.Spawn(identity); err != nil {
		t.Fatal(err)
	}
	for _, role := range []string{"publisher", "controller"} {
		if err := actors.Bind(ActorBinding{ID: identity.ID, Session: identity.Session,
			Generation: identity.Generation, Participant: role, NativeID: map[string]string{
				"publisher": "11", "controller": "45"}[role], CreationFrame: 120}); err != nil {
			t.Fatal(err)
		}
	}
	if !actors.Commandable(identity.ID) || actors.CombatCommandable(identity.ID) {
		t.Fatal("visible larva should be bound but not combat commandable")
	}
	egg := ActorMorph{ID: identity.ID, Session: identity.Session, Generation: 17,
		FromType: "zerg_larva", Type: "zerg_egg", Phase: "incomplete"}
	if err := actors.Morph(egg); err != nil {
		t.Fatal(err)
	}
	if err := actors.Morph(egg); err == nil {
		t.Fatal("stale morph accepted")
	}
	record, _ := actors.Lookup(identity.ID)
	if record.Identity.Type != "zerg_egg" || record.Identity.Phase != "incomplete" ||
		len(record.Bindings) != 2 || record.State != ActorActive || actors.CombatCommandable(identity.ID) {
		t.Fatal("morph lost identity, bindings, or command protection")
	}
	// Same-session recovery can observe a later native type before the bridge
	// receives the individual morph event.
	identity.Type, identity.Phase = "zerg_zergling", "complete"
	if err := actors.Reconcile(identity.Session, []ActorIdentity{identity}); err != nil {
		t.Fatal(err)
	}
	record, _ = actors.Lookup(identity.ID)
	if record.Identity.Type != "zerg_zergling" || len(record.Bindings) != 2 {
		t.Fatal("reconciliation replaced a morphing native unit")
	}
	actors.UnbindParticipant("controller")
	if actors.Commandable(identity.ID) {
		t.Fatal("controller reconnect left a single binding active")
	}
	if err := actors.Bind(ActorBinding{ID: identity.ID, Session: identity.Session,
		Generation: 17, Participant: "controller", NativeID: "45", CreationFrame: 120}); err != nil {
		t.Fatal(err)
	}
	if !actors.Commandable(identity.ID) {
		t.Fatal("controller reconnect did not restore the same actor")
	}
}

func TestIncompleteCombatActorCannotBeCommanded(t *testing.T) {
	identity := testActor()
	identity.Phase = "incomplete"
	actors := NewActorRegistry(identity.Session)
	if err := actors.Spawn(identity); err != nil {
		t.Fatal(err)
	}
	for _, role := range []string{"publisher", "controller"} {
		if err := actors.Bind(ActorBinding{ID: identity.ID, Session: identity.Session,
			Generation: identity.Generation, Participant: role, NativeID: role,
			CreationFrame: 153}); err == nil {
			t.Fatal("invalid native ID accepted")
		}
	}
	for role, native := range map[string]string{"publisher": "12", "controller": "89"} {
		if err := actors.Bind(ActorBinding{ID: identity.ID, Session: identity.Session,
			Generation: identity.Generation, Participant: role, NativeID: native,
			CreationFrame: 153}); err != nil {
			t.Fatal(err)
		}
	}
	if actors.CombatCommandable(identity.ID) {
		t.Fatal("incomplete native actor accepted a combat order")
	}
	if err := actors.Morph(ActorMorph{ID: identity.ID, Session: identity.Session,
		Generation: identity.Generation, FromType: identity.Type, Type: identity.Type,
		Phase: "complete"}); err != nil {
		t.Fatal(err)
	}
	if !actors.CombatCommandable(identity.ID) {
		t.Fatal("completed native combat actor remained unavailable")
	}
}

func TestEggCancellationRetiresOnlyItsNativeIdentity(t *testing.T) {
	larva := ActorIdentity{ID: "openbw:3001", Engine: "openbw", Type: "zerg_larva",
		Owner: 0, Phase: "complete", Generation: 17, Session: "park-session"}
	sibling := larva
	sibling.ID, sibling.Generation = "openbw:3002", 18
	actors := NewActorRegistry(larva.Session)
	for _, identity := range []ActorIdentity{larva, sibling} {
		if err := actors.Spawn(identity); err != nil {
			t.Fatal(err)
		}
	}
	for _, binding := range []ActorBinding{
		{ID: larva.ID, Session: larva.Session, Generation: larva.Generation,
			Participant: "publisher", NativeID: "11", CreationFrame: 120},
		{ID: larva.ID, Session: larva.Session, Generation: larva.Generation,
			Participant: "controller", NativeID: "45", CreationFrame: 120},
		{ID: sibling.ID, Session: sibling.Session, Generation: sibling.Generation,
			Participant: "publisher", NativeID: "12", CreationFrame: 121},
		{ID: sibling.ID, Session: sibling.Session, Generation: sibling.Generation,
			Participant: "controller", NativeID: "46", CreationFrame: 121},
	} {
		if err := actors.Bind(binding); err != nil {
			t.Fatal(err)
		}
	}
	if err := actors.Morph(ActorMorph{ID: larva.ID, Session: larva.Session,
		Generation: larva.Generation, FromType: larva.Type, Type: "zerg_egg",
		Phase: "incomplete"}); err != nil {
		t.Fatal(err)
	}
	if err := actors.Despawn(ActorDespawn{ID: larva.ID, Session: larva.Session,
		Generation: larva.Generation}); err != nil {
		t.Fatal(err)
	}
	if record, ok := actors.Lookup(sibling.ID); !ok || record.State != ActorActive ||
		record.Identity.Type != "zerg_larva" {
		t.Fatal("cancelled egg retired an unrelated larva")
	}
	if err := actors.Morph(ActorMorph{ID: larva.ID, Session: larva.Session,
		Generation: larva.Generation, FromType: "zerg_egg", Type: "zerg_zergling",
		Phase: "complete"}); err == nil {
		t.Fatal("cancelled egg accepted a late completion")
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
		Participant: "publisher", NativeID: "12", CreationFrame: 153}
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

func TestActorRecoveryAtEachInterruptedBinding(t *testing.T) {
	identity := testActor()
	publisher := ActorBinding{ID: identity.ID, Session: identity.Session,
		Generation: identity.Generation, Participant: "publisher", NativeID: "12", CreationFrame: 153}
	controller := publisher
	controller.Participant, controller.NativeID = "controller", "89"
	for _, publisherArrived := range []bool{false, true} {
		actors := NewActorRegistry(identity.Session)
		if err := actors.Spawn(identity); err != nil {
			t.Fatal(err)
		}
		if publisherArrived {
			if err := actors.Bind(publisher); err != nil {
				t.Fatal(err)
			}
		}
		// A replayed authoritative living set must recover either interruption point.
		if err := actors.Reconcile(identity.Session, []ActorIdentity{identity}); err != nil {
			t.Fatal(err)
		}
		if err := actors.Spawn(identity); err != nil {
			t.Fatal(err)
		}
		if err := actors.Bind(publisher); err != nil {
			t.Fatal(err)
		}
		if err := actors.Bind(publisher); err != nil {
			t.Fatal(err)
		}
		if actors.Commandable(identity.ID) {
			t.Fatal("publisher binding made actor commandable")
		}
		if err := actors.Bind(controller); err != nil {
			t.Fatal(err)
		}
		if !actors.Commandable(identity.ID) {
			t.Fatal("recovered actor is not commandable")
		}
		if err := actors.Reconcile(identity.Session, nil); err != nil {
			t.Fatal(err)
		}
		if actors.Commandable(identity.ID) {
			t.Fatal("dead actor was resurrected")
		}
		if err := actors.Spawn(identity); err == nil {
			t.Fatal("tombstoned ID was reused")
		}
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
