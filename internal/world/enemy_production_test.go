package world

import "testing"

func TestEnemyProductionIntentIsFiniteAndRestartSafe(t *testing.T) {
	ledger := NewEnemyProduction(6)
	first, ok := ledger.Plan("session", 120, 37)
	if !ok || first.RequestID != "enemy-train:session:1" || first.State != "pending" {
		t.Fatalf("first intent: %+v %t", first, ok)
	}
	if _, ok := ledger.Plan("session", 121, 37); ok {
		t.Fatal("planned while native result is unknown")
	}
	if !ledger.Resolve(first.RequestID, true, "", 121, 300, 250) {
		t.Fatal("native acceptance not recorded")
	}
	for n := 2; n <= 6; n++ {
		order, ok := ledger.Plan("session", 120+n*100, 37)
		if !ok || order.Sequence != n {
			t.Fatalf("order %d: %+v %t", n, order, ok)
		}
		ledger.Resolve(order.RequestID, true, "", 120+n*100+1, 300-(n-1)*50, 300-n*50)
	}
	if _, ok := ledger.Plan("session", 1000, 37); ok {
		t.Fatal("finite budget exceeded")
	}
	if err := ledger.Validate("session", 6); err != nil {
		t.Fatal(err)
	}
}

func TestEnemyProductionUnknownRequestBlocksRetry(t *testing.T) {
	ledger := NewEnemyProduction(2)
	order, _ := ledger.Plan("session", 100, 42)
	if !ledger.MarkUncertain(order.RequestID) {
		t.Fatal("did not mark uncertain request")
	}
	if _, ok := ledger.Plan("session", 200, 42); ok {
		t.Fatal("uncertain train request was retried")
	}
	if ledger.Resolve(order.RequestID, true, "", 201, 100, 50) {
		t.Fatal("late receipt changed uncertain request")
	}
}

func TestEnemyProductionJournalRejectsUnfundedAcceptance(t *testing.T) {
	ledger := NewEnemyProduction(1)
	order, _ := ledger.Plan("session", 100, 42)
	if !ledger.Resolve(order.RequestID, true, "", 101, 300, 275) {
		t.Fatal("test receipt rejected before journal validation")
	}
	if err := ledger.Validate("session", 1); err == nil {
		t.Fatal("accepted train without native 50-mineral spend was persisted")
	}
}
