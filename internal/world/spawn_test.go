package world

import (
	"encoding/json"
	"fmt"
	"testing"
)

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
	bad.UnitType = "terran_firebat"
	if _, err := q.Submit("session-a", bad); err == nil {
		t.Fatal("non-spawnable production unit accepted")
	}
	bad.UnitType = "zerg_zergling"
	if _, err := NewSpawnQueue("session-a", 5).Submit("session-a", bad); err != nil {
		t.Fatal("existing Zergling wave spawn rejected:", err)
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

func TestPartialBatchJournalRequiresPublisherReconciliation(t *testing.T) {
	q := NewSpawnQueue("session-a", 10)
	request := spawnRequest("partial", 5)
	if _, err := q.Submit("session-a", request); err != nil {
		t.Fatal(err)
	}
	for index := 0; index < 2; index++ {
		execute, _ := q.Next()
		if err := q.Issue(execute); err != nil {
			t.Fatal(err)
		}
		actor := fmt.Sprintf("openbw:%d", 3001+index)
		if err := q.Created(request.RequestID, index, actor, 960, 1024); err != nil {
			t.Fatal(err)
		}
		if err := q.Ready(request.RequestID, index, actor); err != nil {
			t.Fatal(err)
		}
	}
	execute, _ := q.Next()
	if execute.Index != 2 {
		t.Fatal("batch did not advance to third unit")
	}
	if err := q.Issue(execute); err != nil {
		t.Fatal(err)
	}
	encoded, err := json.Marshal(q)
	if err != nil {
		t.Fatal(err)
	}
	var recovered SpawnQueue
	if err := json.Unmarshal(encoded, &recovered); err != nil {
		t.Fatal(err)
	}
	if err := recovered.Recover("session-a", 10); err != nil {
		t.Fatal(err)
	}
	if _, ok := recovered.Next(); ok {
		t.Fatal("bridge restarted an uncertain native creation")
	}
	if err := recovered.NotReceived(request.RequestID, 2); err != nil {
		t.Fatal(err)
	}
	if next, ok := recovered.Next(); !ok || next.Index != 2 {
		t.Fatalf("confirmed unreceived creation did not retry: %+v", next)
	}
	if err := recovered.Issue(execute); err != nil {
		t.Fatal(err)
	}
	if err := recovered.Created(request.RequestID, 2, "openbw:3003", 960, 1024); err != nil {
		t.Fatal(err)
	}
	if err := recovered.NotReceived(request.RequestID, 2); err == nil {
		t.Fatal("created native actor declared absent")
	}
	if err := recovered.Ready(request.RequestID, 2, "openbw:3003"); err != nil {
		t.Fatal(err)
	}
	if next, ok := recovered.Next(); !ok || next.Index != 3 {
		t.Fatalf("partial batch failed to resume: %+v", next)
	}
}

func TestNativeDeathBeforeBindingAfterBridgeRestart(t *testing.T) {
	q := NewSpawnQueue("session-a", 5)
	request := spawnRequest("death-before-binding", 2)
	if _, err := q.Submit("session-a", request); err != nil {
		t.Fatal(err)
	}
	execute, _ := q.Next()
	if err := q.Issue(execute); err != nil {
		t.Fatal(err)
	}
	if err := q.Created(request.RequestID, 0, "openbw:3001", 960, 1024); err != nil {
		t.Fatal(err)
	}
	if err := q.Recover("session-a", 5); err != nil {
		t.Fatal(err)
	}
	if err := q.Fail(request.RequestID, 0, "native_died_before_ready"); err != nil {
		t.Fatal(err)
	}
	status, _ := q.Lookup(request.RequestID)
	if status.Units[0].State != "failed" || status.Units[0].Reason != "native_died_before_ready" {
		t.Fatalf("death result not retained: %+v", status)
	}
	if next, ok := q.Next(); !ok || next.Index != 1 {
		t.Fatalf("batch remained blocked after death: %+v %t", next, ok)
	}
}
