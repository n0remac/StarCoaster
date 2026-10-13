package world

import "testing"

func spawnRequest(id string, count int) SpawnRequest {
	return SpawnRequest{RequestID: id, UnitType: "terran_marine", Count: count,
		X: 960, Y: 1024, Formation: "compact", PlayerID: 2}
}

func TestSpawnQueueSerializesBatchAndPreservesPartialFailure(t *testing.T) {
	q := NewSpawnQueue("session-a", 10)
	req := spawnRequest("spawn-1", 5)
	if _, err := q.Submit("session-a", req); err != nil {
		t.Fatal(err)
	}
	for index := 0; index < 5; index++ {
		execute, ok := q.Next()
		if !ok || execute.Index != index {
			t.Fatalf("next index %d: %+v %t", index, execute, ok)
		}
		if err := q.Issue(execute); err != nil {
			t.Fatal(err)
		}
		if _, ok := q.Next(); ok {
			t.Fatal("second creation issued before identity resolved")
		}
		if index == 2 {
			if err := q.Fail(req.RequestID, index, "occupied"); err != nil {
				t.Fatal(err)
			}
			continue
		}
		actor := "openbw:300" + string(rune('1'+index))
		if err := q.Created(req.RequestID, index, actor, 960+index*32, 1024); err != nil {
			t.Fatal(err)
		}
		if _, ok := q.Next(); ok {
			t.Fatal("next creation issued before controller binding")
		}
		if err := q.Ready(req.RequestID, index, actor); err != nil {
			t.Fatal(err)
		}
	}
	status, _ := q.Lookup(req.RequestID)
	if status.State != "failed" || status.Units[2].Reason != "occupied" || status.Units[4].State != "ready" {
		t.Fatalf("partial batch: %+v", status)
	}
	if repeated, err := q.Submit("session-a", req); err != nil || repeated.State != "failed" {
		t.Fatalf("idempotent request: %+v %v", repeated, err)
	}
	req.Count = 1
	if _, err := q.Submit("session-a", req); err == nil {
		t.Fatal("changed request ID accepted")
	}
}

func TestSpawnQueueValidationCapacityAndUncertainty(t *testing.T) {
	q := NewSpawnQueue("session-a", 5)
	if _, err := q.Submit("old-session", spawnRequest("stale", 1)); err == nil {
		t.Fatal("stale session")
	}
	bad := spawnRequest("bad", 1)
	bad.UnitType = "protoss_zealot"
	if _, err := q.Submit("session-a", bad); err == nil {
		t.Fatal("unsupported type")
	}
	if _, err := q.Submit("session-a", spawnRequest("full", 5)); err != nil {
		t.Fatal(err)
	}
	if _, err := q.Submit("session-a", spawnRequest("overflow", 1)); err == nil {
		t.Fatal("queue overflow")
	}
	execute, _ := q.Next()
	if err := q.Issue(execute); err != nil {
		t.Fatal(err)
	}
	if status, ok := q.Uncertain(); !ok || status.State != "uncertain" {
		t.Fatalf("disconnected issue: %+v %t", status, ok)
	}
	if _, ok := q.Next(); ok {
		t.Fatal("uncertain native creation retried")
	}
	if err := q.Created("full", 0, "openbw:3001", 960, 1024); err != nil {
		t.Fatal(err)
	}
	if err := q.Ready("full", 0, "openbw:3001"); err != nil {
		t.Fatal(err)
	}
	if next, ok := q.Next(); !ok || next.Index != 1 {
		t.Fatalf("reconciled queue: %+v %t", next, ok)
	}
}
