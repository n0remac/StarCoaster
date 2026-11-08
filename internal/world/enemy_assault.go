package world

import (
	"errors"
	"fmt"
	"sort"
)

// EnemyAssault records assignments of observed native actors. It never creates
// a unit or treats a native order receipt as evidence of an actor's birth.
type EnemyAssault struct {
	Version        int                `json:"version"`
	ColonyNativeID int                `json:"colony_native_id,omitempty"`
	Waves          []EnemyAssaultWave `json:"waves"`
}

type EnemyAssaultWave struct {
	ID               string                `json:"id"`
	Sequence         int                   `json:"sequence"`
	SourceBaseID     string                `json:"source_base_id"`
	SourceGeneration int                   `json:"source_generation"`
	SourceNativeID   int                   `json:"source_native_id"`
	Revision         uint64                `json:"revision"`
	Destination      [2]int                `json:"destination"`
	Formation        string                `json:"formation"`
	Desired          int                   `json:"desired"`
	CommittedFrame   int                   `json:"committed_frame"`
	State            string                `json:"state"`
	Actors           []EnemyAssaultActor   `json:"actors"`
	Attempts         []EnemyAssaultAttempt `json:"attempts"`
}

type EnemyAssaultActor struct {
	ID         string `json:"id"`
	Generation uint64 `json:"generation"`
	NativeID   int    `json:"native_id"`
	Type       string `json:"type"`
	State      string `json:"state"`
}

type EnemyAssaultAttempt struct {
	RequestID string   `json:"request_id"`
	Revision  uint64   `json:"revision"`
	Frame     int      `json:"frame"`
	State     string   `json:"state"`
	Reason    string   `json:"reason,omitempty"`
	ActorIDs  []string `json:"actor_ids"`
}

func NewEnemyAssault() *EnemyAssault {
	return &EnemyAssault{Version: 1, Waves: []EnemyAssaultWave{}}
}

func (a *EnemyAssault) BindColony(nativeID int) bool {
	if a == nil || nativeID < 1 || a.ColonyNativeID != 0 && a.ColonyNativeID != nativeID {
		return false
	}
	a.ColonyNativeID = nativeID
	return true
}

func (a *EnemyAssault) AssignedIDs() map[string]bool {
	assigned := map[string]bool{}
	if a != nil {
		for _, wave := range a.Waves {
			for _, actor := range wave.Actors {
				assigned[actor.ID] = true
			}
		}
	}
	return assigned
}

func (a *EnemyAssault) OrderedIDs() map[string]bool {
	ordered := map[string]bool{}
	if a != nil {
		for _, wave := range a.Waves {
			if wave.State != "ordered" && wave.State != "cleared" {
				continue
			}
			for _, actor := range wave.Actors {
				ordered[actor.ID] = true
			}
		}
	}
	return ordered
}

func (a *EnemyAssault) Commit(session string, sequence, frame int, revision uint64,
	colonyNativeID int, destination [2]int, desired int, candidates []EnemyAssaultActor) (EnemyAssaultWave, bool) {
	if a == nil || a.Version != 1 || !identifier.MatchString(session) ||
		sequence != len(a.Waves)+1 || len(a.Waves) >= 12 || frame < 1 || revision < 1 ||
		colonyNativeID < 1 || a.ColonyNativeID != 0 && a.ColonyNativeID != colonyNativeID ||
		destination[0] <= 0 || destination[1] <= 0 ||
		desired < 1 || desired > 12 || len(candidates) == 0 {
		return EnemyAssaultWave{}, false
	}
	assigned := a.AssignedIDs()
	seen := map[string]bool{}
	for _, actor := range candidates {
		if !actorID.MatchString(actor.ID) || actor.Generation == 0 || actor.NativeID < 1 ||
			actor.Type != "zerg_zergling" || actor.State != "alive" || assigned[actor.ID] || seen[actor.ID] {
			return EnemyAssaultWave{}, false
		}
		seen[actor.ID] = true
	}
	sort.Slice(candidates, func(i, j int) bool {
		if candidates[i].Generation != candidates[j].Generation {
			return candidates[i].Generation < candidates[j].Generation
		}
		return candidates[i].ID < candidates[j].ID
	})
	if len(candidates) > desired {
		candidates = candidates[:desired]
	}
	actorIDs := make([]string, 0, len(candidates))
	for _, actor := range candidates {
		actorIDs = append(actorIDs, actor.ID)
	}
	wave := EnemyAssaultWave{ID: fmt.Sprintf("base-%04d", sequence), Sequence: sequence,
		SourceBaseID: "scenario:enemy-hatchery", SourceGeneration: 1,
		SourceNativeID: colonyNativeID, Revision: revision, Destination: destination,
		Formation: "compact", Desired: desired, CommittedFrame: frame, State: "pending",
		Actors: append([]EnemyAssaultActor(nil), candidates...),
		Attempts: []EnemyAssaultAttempt{{RequestID: assaultRequestID(session, sequence, 1),
			Revision: revision, Frame: frame, State: "pending", ActorIDs: actorIDs}}}
	a.Waves = append(a.Waves, wave)
	a.ColonyNativeID = colonyNativeID
	return wave, true
}

func assaultRequestID(session string, sequence, attempt int) string {
	return fmt.Sprintf("enemy-assault:%s:%d:%d", session, sequence, attempt)
}

func (a *EnemyAssault) Pending() (*EnemyAssaultWave, *EnemyAssaultAttempt) {
	if a == nil {
		return nil, nil
	}
	for i := range a.Waves {
		wave := &a.Waves[i]
		if len(wave.Attempts) == 0 {
			continue
		}
		attempt := &wave.Attempts[len(wave.Attempts)-1]
		if attempt.State == "pending" && wave.State == "pending" {
			return wave, attempt
		}
	}
	return nil, nil
}

func (a *EnemyAssault) Resolve(requestID string, accepted bool, reason string, frame int) bool {
	wave, attempt := a.Pending()
	if attempt == nil || attempt.RequestID != requestID || frame < attempt.Frame {
		return false
	}
	if accepted {
		attempt.State, wave.State = "accepted", "ordered"
	} else {
		attempt.State, attempt.Reason, wave.State = "rejected", reason, "route_blocked"
	}
	return true
}

func (a *EnemyAssault) MarkUncertain(requestID string) bool {
	wave, attempt := a.Pending()
	if attempt == nil || attempt.RequestID != requestID {
		return false
	}
	attempt.State, attempt.Reason, wave.State = "uncertain", "native_receipt_missing", "uncertain"
	return true
}

func (a *EnemyAssault) Retry(session string, sequence, frame int, revision uint64) (EnemyAssaultAttempt, bool) {
	if a == nil || sequence < 1 || sequence > len(a.Waves) || revision < 1 {
		return EnemyAssaultAttempt{}, false
	}
	wave := &a.Waves[sequence-1]
	if wave.State != "route_blocked" || len(wave.Attempts) >= 3 ||
		frame < wave.Attempts[len(wave.Attempts)-1].Frame+240 {
		return EnemyAssaultAttempt{}, false
	}
	alive := []string{}
	for _, actor := range wave.Actors {
		if actor.State == "alive" {
			alive = append(alive, actor.ID)
		}
	}
	if len(alive) == 0 {
		return EnemyAssaultAttempt{}, false
	}
	attempt := EnemyAssaultAttempt{RequestID: assaultRequestID(session, sequence, len(wave.Attempts)+1),
		Revision: revision, Frame: frame, State: "pending", ActorIDs: alive}
	wave.Attempts = append(wave.Attempts, attempt)
	wave.State = "pending"
	return attempt, true
}

// MarkDead is called only from a complete native snapshot or actor tombstone.
func (a *EnemyAssault) MarkDead(dead map[string]bool) bool {
	changed := false
	if a == nil {
		return false
	}
	for wi := range a.Waves {
		wave := &a.Waves[wi]
		allDead := true
		for ai := range wave.Actors {
			actor := &wave.Actors[ai]
			if actor.State == "alive" && dead[actor.ID] {
				actor.State = "dead"
				changed = true
			}
			if actor.State == "alive" {
				allDead = false
			}
		}
		if allDead && wave.State != "cleared" && wave.State != "failed" {
			if wave.State == "ordered" {
				wave.State = "cleared"
			} else {
				wave.State = "failed"
				if len(wave.Attempts) > 0 && wave.Attempts[len(wave.Attempts)-1].State == "pending" {
					wave.Attempts[len(wave.Attempts)-1].State = "uncertain"
					wave.Attempts[len(wave.Attempts)-1].Reason = "all_assigned_actors_dead"
				}
			}
			changed = true
		}
	}
	return changed
}

func (a *EnemyAssault) Validate(session string) error {
	if a == nil || a.Version != 1 || !identifier.MatchString(session) ||
		a.ColonyNativeID < 0 || len(a.Waves) > 12 {
		return errors.New("enemy_assault_journal_invalid")
	}
	assigned := map[string]bool{}
	for wi, wave := range a.Waves {
		if wave.Sequence != wi+1 || wave.ID != fmt.Sprintf("base-%04d", wi+1) ||
			wave.SourceBaseID != "scenario:enemy-hatchery" || wave.SourceGeneration != 1 ||
			wave.SourceNativeID < 1 || wave.SourceNativeID != a.ColonyNativeID ||
			wave.Revision < 1 || wave.Formation != "compact" ||
			wave.Destination[0] <= 0 || wave.Destination[1] <= 0 || wave.Desired < 1 || wave.Desired > 12 ||
			wave.CommittedFrame < 1 || len(wave.Actors) < 1 || len(wave.Actors) > wave.Desired ||
			len(wave.Attempts) < 1 || len(wave.Attempts) > 3 ||
			(wave.State != "pending" && wave.State != "ordered" && wave.State != "route_blocked" &&
				wave.State != "uncertain" && wave.State != "failed" && wave.State != "cleared") {
			return errors.New("enemy_assault_wave_invalid")
		}
		for _, actor := range wave.Actors {
			if !actorID.MatchString(actor.ID) || actor.Generation == 0 || actor.NativeID < 1 ||
				actor.Type != "zerg_zergling" || (actor.State != "alive" && actor.State != "dead") ||
				assigned[actor.ID] {
				return errors.New("enemy_assault_actor_invalid")
			}
			assigned[actor.ID] = true
		}
		for ai, attempt := range wave.Attempts {
			if attempt.RequestID != assaultRequestID(session, wave.Sequence, ai+1) ||
				attempt.Revision < wave.Revision || attempt.Frame < wave.CommittedFrame ||
				(attempt.State != "pending" && attempt.State != "accepted" && attempt.State != "rejected" && attempt.State != "uncertain") ||
				(ai < len(wave.Attempts)-1 && attempt.State != "rejected") ||
				len(attempt.ActorIDs) == 0 || len(attempt.ActorIDs) > len(wave.Actors) {
				return errors.New("enemy_assault_attempt_invalid")
			}
			attemptSeen := map[string]bool{}
			for _, id := range attempt.ActorIDs {
				found := false
				for _, actor := range wave.Actors {
					if actor.ID == id {
						found = true
						break
					}
				}
				if !found || attemptSeen[id] {
					return errors.New("enemy_assault_attempt_actor_invalid")
				}
				attemptSeen[id] = true
			}
		}
	}
	return nil
}
