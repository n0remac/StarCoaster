package world

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
)

// ScenarioRuntime is a durable schedule. It records intent before a request is
// submitted; native creation and death are learned only from authoritative
// queue, actor lifecycle, and complete combat snapshots.
type ScenarioRuntime struct {
	Session        string        `json:"session"`
	DefinitionHash string        `json:"definition_hash"`
	StartFrame     int           `json:"start_frame"`
	Started        bool          `json:"started"`
	LastFrame      int           `json:"last_frame"`
	LastSeq        uint64        `json:"last_seq"`
	Waves          []RuntimeWave `json:"waves"`
	Outcome        string        `json:"outcome,omitempty"`
	Error          string        `json:"error,omitempty"`
}
type RuntimeWave struct {
	ID             string        `json:"id"`
	State          string        `json:"state"`
	TriggeredFrame int           `json:"triggered_frame,omitempty"`
	Units          []RuntimeUnit `json:"units,omitempty"`
	Submitted      int           `json:"submitted"`
	Shortfall      int           `json:"shortfall,omitempty"`
	FailureReason  string        `json:"failure_reason,omitempty"`
}
type RuntimeUnit struct {
	GroupIndex int              `json:"group_index"`
	UnitIndex  int              `json:"unit_index"`
	State      string           `json:"state"`
	ActorID    string           `json:"actor_id,omitempty"`
	Attempts   []RuntimeAttempt `json:"attempts,omitempty"`
}
type RuntimeAttempt struct {
	RequestID string `json:"request_id"`
	X         int    `json:"x"`
	Y         int    `json:"y"`
	Reason    string `json:"reason,omitempty"`
}

func ScenarioDefinitionHash(s *Scenario) string {
	data, _ := json.Marshal(s)
	sum := sha256.Sum256(data)
	return hex.EncodeToString(sum[:])
}

func NewScenarioRuntime(s *Scenario, session string) *ScenarioRuntime {
	r := &ScenarioRuntime{Session: session, DefinitionHash: ScenarioDefinitionHash(s)}
	for _, wave := range s.Waves {
		r.Waves = append(r.Waves, RuntimeWave{ID: wave.ID, State: "pending"})
	}
	return r
}

func (r *ScenarioRuntime) Validate(s *Scenario, session string) error {
	if r.Session != session || r.DefinitionHash != ScenarioDefinitionHash(s) {
		return errors.New("scenario_session_or_hash_mismatch")
	}
	if len(r.Waves) != len(s.Waves) {
		return errors.New("scenario_journal_wave_mismatch")
	}
	for i := range r.Waves {
		if r.Waves[i].ID != s.Waves[i].ID {
			return errors.New("scenario_journal_wave_mismatch")
		}
	}
	return nil
}

// AcceptFrame rejects incomplete, stale, or regressing native snapshots. The
// first complete frame after readiness is the scenario's durable origin.
func (r *ScenarioRuntime) AcceptFrame(frame int, seq uint64, complete bool) error {
	if !complete {
		return errors.New("incomplete_native_snapshot")
	}
	if frame < 0 || seq == 0 {
		return errors.New("invalid_native_timeline")
	}
	if r.Started && (frame <= r.LastFrame || seq <= r.LastSeq) {
		r.Error = fmt.Sprintf("native_timeline_mismatch: frame=%d seq=%d after frame=%d seq=%d", frame, seq, r.LastFrame, r.LastSeq)
		return errors.New(r.Error)
	}
	if !r.Started {
		r.StartFrame, r.Started = frame, true
	}
	r.LastFrame, r.LastSeq = frame, seq
	return nil
}

// Trigger fires eligible waves in authored order; every transition is durable
// when the caller saves the runtime before dispatching any request.
func (r *ScenarioRuntime) Trigger(s *Scenario) bool {
	if !r.Started || r.Outcome != "" || r.Error != "" {
		return false
	}
	changed := false
	for i, wave := range s.Waves {
		entry := &r.Waves[i]
		if entry.State != "pending" {
			continue
		}
		fire := false
		switch wave.Trigger.Type {
		case "on_ready":
			fire = true
		case "elapsed_frames":
			fire = wave.Trigger.Frames != nil && r.LastFrame-r.StartFrame >= *wave.Trigger.Frames
		case "wave_cleared":
			for _, prior := range r.Waves {
				if prior.ID == wave.Trigger.WaveID && prior.State == "cleared" {
					fire = true
				}
			}
		}
		if !fire {
			continue
		}
		entry.State, entry.TriggeredFrame = "triggered", r.LastFrame
		for gi, group := range wave.Groups {
			for ui := 0; ui < group.Count; ui++ {
				entry.Units = append(entry.Units, RuntimeUnit{GroupIndex: gi, UnitIndex: ui, State: "planned"})
			}
		}
		changed = true
	}
	return changed
}

// NextPlanned returns one unit that needs initial placement or a confirmed
// placement retry. A pending native request is never replaced speculatively.
func (r *ScenarioRuntime) NextPlanned() (int, int, bool) {
	if r.Outcome != "" || r.Error != "" {
		return 0, 0, false
	}
	for wi := range r.Waves {
		wave := &r.Waves[wi]
		if wave.State != "triggered" && wave.State != "spawning" {
			continue
		}
		for ui := range wave.Units {
			if wave.Units[ui].State == "planned" {
				return wi, ui, true
			}
		}
	}
	return 0, 0, false
}

func (r *ScenarioRuntime) Intent(wi, ui int, position Point) SpawnRequest {
	wave := &r.Waves[wi]
	unit := &wave.Units[ui]
	attempt := len(unit.Attempts)
	key := fmt.Sprintf("%s/%s/%d/%d/%d", r.Session, wave.ID, unit.GroupIndex, unit.UnitIndex, attempt)
	sum := sha256.Sum256([]byte(key))
	id := "scenario:" + hex.EncodeToString(sum[:16])
	unit.Attempts = append(unit.Attempts, RuntimeAttempt{RequestID: id, X: position.X, Y: position.Y})
	unit.State, wave.State = "submitted", "spawning"
	wave.Submitted++
	return SpawnRequest{RequestID: id, UnitType: "zerg_zergling", Count: 1,
		X: position.X, Y: position.Y, Formation: "compact", PlayerID: 0}
}

// Reconcile never interprets a missing snapshot actor as dead on its own.
// removed must come from the native actor lifecycle, while living is drawn
// from the same complete accepted native snapshot.
func (r *ScenarioRuntime) Reconcile(queue *SpawnQueue, living map[string]bool, removed map[string]bool) bool {
	if r.Error != "" || queue == nil {
		return false
	}
	changed := false
	for wi := range r.Waves {
		wave := &r.Waves[wi]
		if wave.State == "pending" || wave.State == "failed" || wave.State == "cleared" {
			continue
		}
		success, failed, settled, allDead := 0, 0, true, true
		for ui := range wave.Units {
			unit := &wave.Units[ui]
			if unit.State == "dead" {
				success++
				continue
			}
			if unit.State == "failed" {
				failed++
				continue
			}
			if len(unit.Attempts) == 0 {
				settled, allDead = false, false
				continue
			}
			attempt := &unit.Attempts[len(unit.Attempts)-1]
			status, ok := queue.Lookup(attempt.RequestID)
			if !ok {
				settled, allDead = false, false
				continue
			} // intent persisted before queue submission
			state := status.Units[0].State
			if state == "failed" || state == "rejected" {
				attempt.Reason = status.Units[0].Reason
				if unit.ActorID == "" && retryablePlacement(attempt.Reason) {
					unit.State = "planned"
				} else {
					unit.State = "failed"
				}
				changed = true
				if unit.State == "failed" {
					failed++
				} else {
					settled, allDead = false, false
				}
				continue
			}
			if state != "ready" {
				settled, allDead = false, false
				continue
			}
			actor := status.Units[0].ActorID
			if actor == "" {
				settled, allDead = false, false
				continue
			}
			if unit.ActorID != actor {
				unit.ActorID, unit.State, changed = actor, "ready", true
			}
			success++
			if removed[actor] && !living[actor] {
				unit.State, changed = "dead", true
			} else {
				allDead = false
			}
		}
		if wave.Shortfall != failed {
			wave.Shortfall, changed = failed, true
		}
		if !settled {
			continue
		}
		if success == 0 {
			wave.State, changed = "failed", true
			if wave.FailureReason == "" {
				wave.FailureReason = "no_confirmed_native_actors"
			}
		} else if allDead {
			wave.State, changed = "cleared", true
		} else if wave.State != "active" {
			wave.State, changed = "active", true
		}
	}
	return changed
}

func retryablePlacement(reason string) bool {
	return reason == "invalid_or_occupied_native_position" || reason == "native_unwalkable_position" || reason == "occupied"
}

func (r *ScenarioRuntime) AllWavesCleared() bool {
	if len(r.Waves) == 0 || r.Error != "" {
		return false
	}
	for _, wave := range r.Waves {
		if wave.State != "cleared" {
			return false
		}
	}
	return true
}
