package world

import (
	"encoding/json"
	"testing"
)

func runtimeFixture(t *testing.T) (*Scenario, *ScenarioRuntime) {
	t.Helper()
	s := validV2(t)
	r := NewScenarioRuntime(&s, "session-a")
	return &s, r
}

func TestScenarioRuntimeTriggersAndNoPrematureVictory(t *testing.T) {
	s, r := runtimeFixture(t)
	if err := r.AcceptFrame(100, 1, true); err != nil {
		t.Fatal(err)
	}
	if !r.Trigger(s) || r.Waves[0].State != "triggered" || r.Waves[1].State != "triggered" || r.Waves[2].State != "pending" {
		t.Fatalf("wrong first-frame triggers: %+v", r.Waves)
	}
	if r.AllWavesCleared() {
		t.Fatal("pending dependent wave allowed victory")
	}
	queue := NewSpawnQueue("session-a", 64)
	for wi := 0; wi < 2; wi++ {
		request := r.Intent(wi, 0, Point{X: 1424 + wi*32, Y: 1808})
		if request.Count != 1 || request.UnitType != "zerg_zergling" {
			t.Fatalf("wrong request: %+v", request)
		}
		if _, err := queue.Submit("session-a", request); err != nil {
			t.Fatal(err)
		}
		execute, _ := queue.Next()
		if err := queue.Issue(execute); err != nil {
			t.Fatal(err)
		}
		actor := "openbw:" + string(rune('1'+wi))
		if err := queue.Created(request.RequestID, 0, actor, request.X, request.Y); err != nil {
			t.Fatal(err)
		}
		if err := queue.Ready(request.RequestID, 0, actor); err != nil {
			t.Fatal(err)
		}
	}
	if !r.Reconcile(queue, map[string]bool{"openbw:1": true, "openbw:2": true}, nil) {
		t.Fatal("ready state not reconciled")
	}
	if r.AllWavesCleared() {
		t.Fatal("living wave allowed victory")
	}
	if !r.Reconcile(queue, nil, map[string]bool{"openbw:1": true, "openbw:2": true}) {
		t.Fatal("native death not reconciled")
	}
	if r.Waves[0].State != "cleared" || r.Waves[1].State != "cleared" {
		t.Fatalf("wave not cleared: %+v", r.Waves)
	}
	if r.AllWavesCleared() {
		t.Fatal("dependent wave still pending")
	}
	if !r.Trigger(s) || r.Waves[2].State != "triggered" {
		t.Fatalf("dependent trigger: %+v", r.Waves[2])
	}
}

func TestScenarioRuntimeRejectsIncompleteAndRegressingFrames(t *testing.T) {
	_, r := runtimeFixture(t)
	if err := r.AcceptFrame(100, 1, false); err == nil || r.Started {
		t.Fatalf("incomplete accepted: %v", err)
	}
	if err := r.AcceptFrame(100, 1, true); err != nil {
		t.Fatal(err)
	}
	if err := r.AcceptFrame(99, 2, true); err == nil || r.Error == "" {
		t.Fatal("regressing frame accepted")
	}
	if err := r.AcceptFrame(101, 3, true); err != nil {
		t.Fatal(err)
	}
	if _, _, ok := r.NextPlanned(); ok {
		t.Fatal("unhealthy timeline scheduled work")
	}
}

func TestScenarioRuntimeUncertainAndPartialFailure(t *testing.T) {
	s, r := runtimeFixture(t)
	s.Waves = s.Waves[:1]
	s.Waves[0].Groups[0].Count = 2
	r = NewScenarioRuntime(s, "session-a")
	if err := r.AcceptFrame(10, 1, true); err != nil {
		t.Fatal(err)
	}
	r.Trigger(s)
	queue := NewSpawnQueue("session-a", 64)
	a := r.Intent(0, 0, Point{X: 100, Y: 100})
	b := r.Intent(0, 1, Point{X: 132, Y: 100})
	for _, req := range []SpawnRequest{a, b} {
		if _, err := queue.Submit("session-a", req); err != nil {
			t.Fatal(err)
		}
	}
	execute, _ := queue.Next()
	if err := queue.Issue(execute); err != nil {
		t.Fatal(err)
	}
	if _, ok := queue.Uncertain(); !ok {
		t.Fatal("expected uncertain creation")
	}
	r.Reconcile(queue, nil, nil)
	if r.Waves[0].State == "cleared" || r.AllWavesCleared() {
		t.Fatal("uncertain creation allowed victory")
	}
	if err := queue.Fail(a.RequestID, 0, "invalid_or_occupied_native_position"); err != nil {
		t.Fatal(err)
	}
	r.Reconcile(queue, nil, nil)
	if r.Waves[0].Units[0].State != "planned" {
		t.Fatal("confirmed placement failure did not permit fallback")
	}
	if a.RequestID == r.Intent(0, 0, Point{X: 164, Y: 100}).RequestID {
		t.Fatal("fallback reused request ID")
	}
}

func TestScenarioRuntimePartialAndTotalFailureOutcomes(t *testing.T) {
	s, r := runtimeFixture(t)
	s.Waves = s.Waves[:1]
	s.Waves[0].Groups[0].Count = 2
	r = NewScenarioRuntime(s, "session-a")
	if err := r.AcceptFrame(10, 1, true); err != nil {
		t.Fatal(err)
	}
	r.Trigger(s)
	q := NewSpawnQueue("session-a", 64)
	a := r.Intent(0, 0, Point{X: 100, Y: 100})
	b := r.Intent(0, 1, Point{X: 132, Y: 100})
	for _, request := range []SpawnRequest{a, b} {
		if _, err := q.Submit("session-a", request); err != nil {
			t.Fatal(err)
		}
	}
	first, _ := q.Next()
	if err := q.Issue(first); err != nil {
		t.Fatal(err)
	}
	if err := q.Fail(a.RequestID, 0, "native_owner_unavailable"); err != nil {
		t.Fatal(err)
	}
	second, _ := q.Next()
	if err := q.Issue(second); err != nil {
		t.Fatal(err)
	}
	if err := q.Created(b.RequestID, 0, "openbw:2", 132, 100); err != nil {
		t.Fatal(err)
	}
	if err := q.Ready(b.RequestID, 0, "openbw:2"); err != nil {
		t.Fatal(err)
	}
	r.Reconcile(q, map[string]bool{"openbw:2": true}, nil)
	if r.Waves[0].State != "active" || r.Waves[0].Shortfall != 1 || r.AllWavesCleared() {
		t.Fatalf("partial wave premature: %+v", r.Waves[0])
	}
	r.Reconcile(q, nil, map[string]bool{"openbw:2": true})
	if r.Waves[0].State != "cleared" || r.Waves[0].Shortfall != 1 {
		t.Fatalf("partial wave not cleared: %+v", r.Waves[0])
	}
	allFailed := NewScenarioRuntime(s, "session-a")
	if err := allFailed.AcceptFrame(10, 1, true); err != nil {
		t.Fatal(err)
	}
	allFailed.Trigger(s)
	allFailed.Waves[0].Units[0].State = "failed"
	allFailed.Waves[0].Units[1].State = "failed"
	allFailed.Reconcile(NewSpawnQueue("session-a", 64), nil, nil)
	if allFailed.Waves[0].State != "failed" || allFailed.AllWavesCleared() {
		t.Fatal("zero-success wave allowed victory")
	}
}

func TestMixedWaveIntentRecoveryAndDeath(t *testing.T) {
	s, r := runtimeFixture(t)
	s.Waves = s.Waves[:1]
	s.Waves[0].Groups = []WaveGroup{
		{UnitType: "zerg_zergling", Count: 1, SpawnZone: "east-entrance"},
		{UnitType: "zerg_hydralisk", Count: 1, SpawnZone: "east-entrance"},
		{UnitType: "zerg_ultralisk", Count: 1, SpawnZone: "east-entrance"},
	}
	r = NewScenarioRuntime(s, "session-a")
	if err := r.AcceptFrame(100, 1, true); err != nil {
		t.Fatal(err)
	}
	r.Trigger(s)
	q := NewSpawnQueue("session-a", 64)
	for i, kind := range []string{"zerg_zergling", "zerg_hydralisk", "zerg_ultralisk"} {
		request := r.Intent(0, i, Point{X: 100 + i*32, Y: 100})
		if request.UnitType != kind {
			t.Fatalf("intent %d: %s", i, request.UnitType)
		}
		if _, err := q.Submit("session-a", request); err != nil {
			t.Fatal(err)
		}
	}
	data, err := json.Marshal(r)
	if err != nil {
		t.Fatal(err)
	}
	var recovered ScenarioRuntime
	if err := json.Unmarshal(data, &recovered); err != nil {
		t.Fatal(err)
	}
	if err := recovered.Validate(s, "session-a"); err != nil {
		t.Fatal(err)
	}
	for i, kind := range []string{"zerg_zergling", "zerg_hydralisk", "zerg_ultralisk"} {
		unit := recovered.Waves[0].Units[i]
		if unit.UnitType != kind || unit.Attempts[0].RequestID == "" {
			t.Fatalf("lost intent: %+v", unit)
		}
	}
	first, _ := q.Next()
	if err := q.Issue(first); err != nil {
		t.Fatal(err)
	}
	if err := q.Fail(first.RequestID, 0, "invalid_native_position"); err != nil {
		t.Fatal(err)
	}
	recovered.Reconcile(q, nil, nil)
	if retry := recovered.Intent(0, 0, Point{X: 200, Y: 100}); retry.UnitType != "zerg_zergling" || retry.RequestID == first.RequestID {
		t.Fatalf("retry changed identity: %+v", retry)
	}
	for i := 1; i < 3; i++ {
		req := recovered.Waves[0].Units[i].Attempts[0]
		for {
			next, ok := q.Next()
			if !ok {
				t.Fatal("missing queued request")
			}
			if err := q.Issue(next); err != nil {
				t.Fatal(err)
			}
			if next.RequestID == req.RequestID {
				actor := "openbw:" + string(rune('1'+i))
				if err := q.Created(req.RequestID, 0, actor, req.X, req.Y); err != nil {
					t.Fatal(err)
				}
				if err := q.Ready(req.RequestID, 0, actor); err != nil {
					t.Fatal(err)
				}
				break
			}
		}
	}
	recovered.Reconcile(q, map[string]bool{"openbw:2": true, "openbw:3": true}, nil)
	if recovered.Waves[0].State == "cleared" {
		t.Fatal("living mixed enemies cleared wave")
	}
	// A missing unit type can only be recovered from an unchanged Zergling group.
	recovered.Waves[0].Units[1].UnitType = ""
	if err := recovered.Validate(s, "session-a"); err == nil {
		t.Fatal("ambiguous legacy type accepted")
	}
}
