package world

import (
	"errors"
	"fmt"
)

// A request identifies an intent. Native actor IDs are assigned only by OpenBW.
type SpawnRequest struct {
	RequestID string `json:"request_id"`
	UnitType  string `json:"unit_type"`
	Count     int    `json:"count"`
	X         int    `json:"x"`
	Y         int    `json:"y"`
	Formation string `json:"formation"`
	PlayerID  int    `json:"player_id"`
}

type SpawnExecute struct {
	RequestID string `json:"request_id"`
	Index     int    `json:"index"`
	UnitType  string `json:"unit_type"`
	X         int    `json:"x"`
	Y         int    `json:"y"`
}

type SpawnUnitResult struct {
	Index   int    `json:"index"`
	State   string `json:"state"`
	ActorID string `json:"actor_id,omitempty"`
	X       int    `json:"x,omitempty"`
	Y       int    `json:"y,omitempty"`
	Reason  string `json:"reason,omitempty"`
}

type SpawnStatus struct {
	RequestID string            `json:"request_id"`
	State     string            `json:"state"`
	Reason    string            `json:"reason,omitempty"`
	Units     []SpawnUnitResult `json:"units"`
}

type spawnEntry struct {
	Request SpawnRequest `json:"request"`
	Status  SpawnStatus  `json:"status"`
}

// SpawnQueue serializes native creation. It never treats a sent command as a
// created unit. A disrupted issue remains uncertain until native reconciliation.
type SpawnQueue struct {
	Session string                 `json:"session"`
	Limit   int                    `json:"limit"`
	Entries map[string]*spawnEntry `json:"entries"`
	Order   []string               `json:"order"`
	Active  string                 `json:"active"`
}

func NewSpawnQueue(session string, limit int) *SpawnQueue {
	return &SpawnQueue{Session: session, Limit: limit, Entries: map[string]*spawnEntry{}}
}

// Recover conservatively treats any command that may have reached OpenBW as
// uncertain. The publisher must report its outcome before another is issued.
func (q *SpawnQueue) Recover(session string, limit int) error {
	if q.Session != session || q.Entries == nil || q.Limit < 1 {
		return errors.New("invalid_spawn_journal")
	}
	q.Limit = limit
	if q.Active != "" {
		entry := q.Entries[q.Active]
		if entry == nil {
			return errors.New("invalid_active_spawn_journal")
		}
		uncertain := false
		for _, unit := range entry.Status.Units {
			if unit.State == "uncertain" {
				uncertain = true
			}
		}
		if !uncertain {
			if _, ok := q.Uncertain(); !ok {
				return errors.New("invalid_active_spawn_journal")
			}
		}
	}
	return nil
}

func (q *SpawnQueue) Request(id string) (SpawnRequest, bool) {
	entry := q.Entries[id]
	if entry == nil {
		return SpawnRequest{}, false
	}
	return entry.Request, true
}

// PruneSettled removes only journal entries whose native creation has reached
// a terminal queue state. Callers must first persist the matching wave journal.
func (q *SpawnQueue) PruneSettled(ids []string) int {
	remove := map[string]bool{}
	for _, id := range ids {
		entry := q.Entries[id]
		if entry == nil || q.Active == id {
			continue
		}
		settled := true
		for _, unit := range entry.Status.Units {
			if unit.State != "ready" && unit.State != "failed" && unit.State != "rejected" {
				settled = false
				break
			}
		}
		if settled {
			remove[id] = true
		}
	}
	if len(remove) == 0 {
		return 0
	}
	order := q.Order[:0]
	for _, id := range q.Order {
		if remove[id] {
			delete(q.Entries, id)
		} else {
			order = append(order, id)
		}
	}
	q.Order = order
	return len(remove)
}

func (q *SpawnQueue) FindActor(actor string) (string, int, bool) {
	for id, entry := range q.Entries {
		for _, unit := range entry.Status.Units {
			if unit.ActorID == actor {
				return id, unit.Index, true
			}
		}
	}
	return "", 0, false
}

func (q *SpawnQueue) Unresolved() (SpawnExecute, bool) {
	if q.Active == "" {
		return SpawnExecute{}, false
	}
	entry := q.Entries[q.Active]
	if entry == nil {
		return SpawnExecute{}, false
	}
	for _, unit := range entry.Status.Units {
		if unit.State == "issued" || unit.State == "created" || unit.State == "uncertain" {
			return SpawnExecute{RequestID: q.Active, Index: unit.Index,
				UnitType: entry.Request.UnitType, X: entry.Request.X, Y: entry.Request.Y}, true
		}
	}
	return SpawnExecute{}, false
}

// Only an explicit publisher report that it never received the command can
// turn an uncertain creation back into a safe queued creation.
func (q *SpawnQueue) NotReceived(id string, index int) error {
	if q.Active != id {
		return errors.New("unexpected_unreceived_spawn")
	}
	entry := q.Entries[id]
	if entry == nil || index < 0 || index >= len(entry.Status.Units) ||
		entry.Status.Units[index].State != "uncertain" || entry.Status.Units[index].ActorID != "" {
		return errors.New("invalid_unreceived_spawn")
	}
	entry.Status.Units[index] = SpawnUnitResult{Index: index, State: "queued"}
	q.Active = ""
	q.summarize(entry)
	return nil
}

func (q *SpawnQueue) Submit(session string, request SpawnRequest) (SpawnStatus, error) {
	if session != q.Session {
		return SpawnStatus{}, errors.New("stale_session")
	}
	if prior := q.Entries[request.RequestID]; prior != nil {
		if prior.Request != request {
			return SpawnStatus{}, errors.New("conflicting_request_id")
		}
		return prior.Status, nil
	}
	_, supportedUnit := SupportedUnit(request.UnitType)
	if !identifier.MatchString(request.RequestID) || request.Count < 1 || request.Count > 5 ||
		!supportedUnit ||
		request.Formation != "compact" || request.PlayerID < 0 || request.PlayerID > 255 {
		return SpawnStatus{}, errors.New("invalid_spawn_request")
	}
	if q.PendingCount()+request.Count > q.Limit {
		return SpawnStatus{}, errors.New("spawn_queue_full")
	}
	status := SpawnStatus{RequestID: request.RequestID, State: "queued", Units: make([]SpawnUnitResult, request.Count)}
	for i := range status.Units {
		status.Units[i] = SpawnUnitResult{Index: i, State: "queued"}
	}
	q.Entries[request.RequestID] = &spawnEntry{Request: request, Status: status}
	q.Order = append(q.Order, request.RequestID)
	return status, nil
}

func (q *SpawnQueue) Lookup(id string) (SpawnStatus, bool) {
	entry := q.Entries[id]
	if entry == nil {
		return SpawnStatus{}, false
	}
	return entry.Status, true
}

func (q *SpawnQueue) PendingCount() int {
	n := 0
	for _, entry := range q.Entries {
		for _, unit := range entry.Status.Units {
			if unit.State != "ready" && unit.State != "failed" && unit.State != "rejected" {
				n++
			}
		}
	}
	return n
}

func (q *SpawnQueue) Next() (SpawnExecute, bool) {
	if q.Active != "" {
		return SpawnExecute{}, false
	}
	for _, id := range q.Order {
		entry := q.Entries[id]
		for _, unit := range entry.Status.Units {
			if unit.State == "queued" {
				return SpawnExecute{RequestID: id, Index: unit.Index,
					UnitType: entry.Request.UnitType, X: entry.Request.X, Y: entry.Request.Y}, true
			}
		}
	}
	return SpawnExecute{}, false
}

func (q *SpawnQueue) Issue(execute SpawnExecute) error {
	next, ok := q.Next()
	if !ok || next != execute {
		return errors.New("unexpected_spawn_issue")
	}
	q.Active = execute.RequestID
	return q.transition(execute.RequestID, execute.Index, "issued", "", "", 0, 0)
}

func (q *SpawnQueue) Created(id string, index int, actor string, x, y int) error {
	if !actorID.MatchString(actor) {
		return errors.New("invalid_spawn_actor")
	}
	if priorID, priorIndex, found := q.FindActor(actor); found && (priorID != id || priorIndex != index) {
		return errors.New("spawn_actor_already_assigned")
	}
	if entry := q.Entries[id]; entry != nil && index >= 0 && index < len(entry.Status.Units) {
		unit := entry.Status.Units[index]
		if unit.ActorID == actor && (unit.State == "created" || unit.State == "ready") {
			return nil
		}
	}
	return q.transition(id, index, "created", actor, "", x, y)
}

func (q *SpawnQueue) Ready(id string, index int, actorID string) error {
	entry := q.Entries[id]
	if entry == nil || index < 0 || index >= len(entry.Status.Units) ||
		entry.Status.Units[index].ActorID != actorID {
		return errors.New("unknown_spawn_actor")
	}
	return q.transition(id, index, "ready", actorID, "", 0, 0)
}

func (q *SpawnQueue) Fail(id string, index int, reason string) error {
	if reason == "" {
		reason = "native_rejected"
	}
	return q.transition(id, index, "failed", "", reason, 0, 0)
}

func (q *SpawnQueue) Uncertain() (SpawnStatus, bool) {
	if q.Active == "" {
		return SpawnStatus{}, false
	}
	id := q.Active
	for _, unit := range q.Entries[id].Status.Units {
		if unit.State == "issued" || unit.State == "created" {
			_ = q.transition(id, unit.Index, "uncertain", unit.ActorID, "native_reconciliation_required", unit.X, unit.Y)
			return q.Entries[id].Status, true
		}
	}
	return SpawnStatus{}, false
}

func (q *SpawnQueue) Cancel(id string) (SpawnStatus, error) {
	entry := q.Entries[id]
	if entry == nil {
		return SpawnStatus{}, errors.New("unknown_spawn_request")
	}
	for i, unit := range entry.Status.Units {
		if unit.State == "queued" {
			entry.Status.Units[i].State = "rejected"
			entry.Status.Units[i].Reason = "cancelled"
		}
	}
	q.summarize(entry)
	return entry.Status, nil
}

func (q *SpawnQueue) transition(id string, index int, state, actor, reason string, x, y int) error {
	entry := q.Entries[id]
	if entry == nil || index < 0 || index >= len(entry.Status.Units) {
		return errors.New("unknown_spawn_unit")
	}
	unit := &entry.Status.Units[index]
	if unit.State == state && (actor == "" || unit.ActorID == actor) {
		return nil
	}
	allowed := (unit.State == "queued" && state == "issued") ||
		(unit.State == "issued" && (state == "created" || state == "failed" || state == "uncertain")) ||
		(unit.State == "created" && (state == "ready" || state == "failed" || state == "uncertain")) ||
		(unit.State == "uncertain" && (state == "created" || state == "failed" || state == "ready"))
	if !allowed {
		return fmt.Errorf("invalid_spawn_transition: %s to %s", unit.State, state)
	}
	unit.State = state
	if actor != "" {
		unit.ActorID = actor
	}
	if reason != "" {
		unit.Reason = reason
	}
	if state == "created" {
		unit.X, unit.Y = x, y
		unit.Reason = ""
	}
	if state == "ready" {
		unit.Reason = ""
	}
	if state == "ready" || state == "failed" {
		q.Active = ""
	}
	q.summarize(entry)
	return nil
}

func (q *SpawnQueue) summarize(entry *spawnEntry) {
	counts := map[string]int{}
	for _, unit := range entry.Status.Units {
		counts[unit.State]++
	}
	switch {
	case counts["uncertain"] > 0:
		entry.Status.State = "uncertain"
	case counts["created"] > 0:
		entry.Status.State = "created"
	case counts["issued"] > 0:
		entry.Status.State = "issued"
	case counts["queued"] > 0:
		entry.Status.State = "queued"
	case counts["failed"]+counts["rejected"] > 0:
		entry.Status.State = "failed"
	default:
		entry.Status.State = "ready"
	}
}
