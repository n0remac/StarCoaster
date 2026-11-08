package world

import "testing"

func assaultCandidates(ids ...string) []EnemyAssaultActor {
	out := make([]EnemyAssaultActor, 0, len(ids))
	for i, id := range ids {
		out = append(out, EnemyAssaultActor{ID: id, Generation: uint64(i + 1),
			NativeID: i + 40, Type: "zerg_zergling", State: "alive"})
	}
	return out
}

func TestEnemyAssaultUsesOnlyAvailableCompletedPair(t *testing.T) {
	ledger := NewEnemyAssault()
	actors := assaultCandidates("openbw:3001", "openbw:3002")
	wave, ok := ledger.Commit("session", 1, 7200, 1, 5, [2]int{800, 900}, 8, actors)
	if !ok || wave.Desired != 8 || len(wave.Actors) != 2 || wave.SourceBaseID != "scenario:enemy-hatchery" ||
		wave.Attempts[0].RequestID != "enemy-assault:session:1:1" {
		t.Fatalf("short native pair not committed correctly: %+v %t", wave, ok)
	}
	if _, ok := ledger.Commit("session", 2, 10080, 1, 5, [2]int{800, 900}, 8, actors); ok {
		t.Fatal("assigned Zergling was assigned to a second wave")
	}
	if err := ledger.Validate("session"); err != nil {
		t.Fatal(err)
	}
}

func TestEnemyAssaultRouteFailureRetryAndLateReceipt(t *testing.T) {
	ledger := NewEnemyAssault()
	wave, _ := ledger.Commit("session", 1, 7200, 1, 5, [2]int{800, 900}, 2,
		assaultCandidates("openbw:3001", "openbw:3002"))
	request := wave.Attempts[0].RequestID
	if !ledger.Resolve(request, false, "native_route_unavailable", 7201) {
		t.Fatal("route result lost")
	}
	if _, ok := ledger.Retry("session", 1, 7300, 1); ok {
		t.Fatal("retried before backoff")
	}
	retry, ok := ledger.Retry("session", 1, 7450, 2)
	if !ok || retry.RequestID != "enemy-assault:session:1:2" {
		t.Fatalf("retry: %+v %t", retry, ok)
	}
	if ledger.Resolve(request, true, "", 7451) {
		t.Fatal("late receipt overrode newer attempt")
	}
	if !ledger.Resolve(retry.RequestID, true, "", 7452) {
		t.Fatal("native acceptance lost")
	}
	if _, ok := ledger.Retry("session", 1, 7700, 2); ok {
		t.Fatal("accepted wave reissued")
	}
	if err := ledger.Validate("session"); err != nil {
		t.Fatal(err)
	}
}

func TestEnemyAssaultDeathAndUnknownReceiptRemainSafe(t *testing.T) {
	ledger := NewEnemyAssault()
	wave, _ := ledger.Commit("session", 1, 7200, 1, 5, [2]int{800, 900}, 2,
		assaultCandidates("openbw:3001", "openbw:3002"))
	ledger.MarkDead(map[string]bool{"openbw:3001": true})
	if !ledger.MarkUncertain(wave.Attempts[0].RequestID) {
		t.Fatal("unknown receipt not recorded")
	}
	if _, ok := ledger.Retry("session", 1, 7500, 2); ok {
		t.Fatal("uncertain native order retried")
	}
	if ledger.Resolve(wave.Attempts[0].RequestID, true, "", 7501) {
		t.Fatal("late acceptance changed uncertain order")
	}
	if err := ledger.Validate("session"); err != nil {
		t.Fatal(err)
	}
}
