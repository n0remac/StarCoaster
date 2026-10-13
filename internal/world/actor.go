package world

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"regexp"
	"sort"
)

var actorID = regexp.MustCompile(`^openbw:[0-9]+$`)
var nativeActorID = regexp.MustCompile(`^[0-9]+$`)

// ActorIdentity is the stable identity published by OpenBW. Generation is an
// engine creation token, never a position or a bridge-assigned sequence.
type ActorIdentity struct {
	ID         string `json:"id"`
	Engine     string `json:"engine"`
	Type       string `json:"type"`
	Owner      int    `json:"owner"`
	Generation uint64 `json:"generation"`
	Session    string `json:"session"`
}

type ActorBinding struct {
	ID          string `json:"id"`
	Session     string `json:"session"`
	Generation  uint64 `json:"generation"`
	Participant string `json:"participant"`
	NativeID    string `json:"native_id"`
}

type ActorDespawn struct {
	ID         string `json:"id"`
	Session    string `json:"session"`
	Generation uint64 `json:"generation"`
}

type ActorReconcile struct {
	Living []ActorIdentity `json:"living"`
}

type ActorLifecycle string

const (
	ActorSpawning ActorLifecycle = "spawning"
	ActorActive   ActorLifecycle = "active"
	ActorRemoved  ActorLifecycle = "removed"
)

type ActorRecord struct {
	Identity ActorIdentity
	State    ActorLifecycle
	Bindings map[string]ActorBinding
}

// ActorRegistry stores lifecycle facts only. Combat snapshots own movement,
// health, animation and other frequently changing values.
type ActorRegistry struct {
	Session string
	records map[string]*ActorRecord
	native  map[string]string
}

func NewActorRegistry(session string) *ActorRegistry {
	return &ActorRegistry{Session: session, records: map[string]*ActorRecord{}, native: map[string]string{}}
}

func decodeActorPayload(raw json.RawMessage, value any) error {
	decoder := json.NewDecoder(bytes.NewReader(raw))
	decoder.DisallowUnknownFields()
	return decoder.Decode(value)
}

func (identity ActorIdentity) Validate(session string) error {
	if identity.Session != session || !identifier.MatchString(identity.Session) ||
		!actorID.MatchString(identity.ID) || identity.Engine != "openbw" ||
		(identity.Type != "terran_marine" && identity.Type != "zerg_zergling") ||
		identity.Owner < 0 || identity.Owner > 15 || identity.Generation == 0 {
		return errors.New("invalid actor identity or session")
	}
	return nil
}

func (binding ActorBinding) Validate(session string) error {
	if binding.Session != session || !actorID.MatchString(binding.ID) || binding.Generation == 0 ||
		(binding.Participant != "publisher" && binding.Participant != "controller") ||
		!nativeActorID.MatchString(binding.NativeID) {
		return errors.New("invalid actor binding")
	}
	return nil
}

func (event ActorDespawn) Validate(session string) error {
	if event.Session != session || !actorID.MatchString(event.ID) || event.Generation == 0 {
		return errors.New("invalid actor despawn")
	}
	return nil
}

func (r *ActorRegistry) Reset(session string) error {
	if !identifier.MatchString(session) || session == r.Session {
		return errors.New("invalid or unchanged actor session")
	}
	r.Session = session
	r.records = map[string]*ActorRecord{}
	r.native = map[string]string{}
	return nil
}

func (r *ActorRegistry) Spawn(identity ActorIdentity) error {
	if err := identity.Validate(r.Session); err != nil {
		return err
	}
	if prior := r.records[identity.ID]; prior != nil {
		if prior.Identity == identity && prior.State != ActorRemoved {
			return nil
		}
		return errors.New("actor ID already used")
	}
	r.records[identity.ID] = &ActorRecord{Identity: identity, State: ActorSpawning,
		Bindings: map[string]ActorBinding{}}
	return nil
}

func (r *ActorRegistry) Bind(binding ActorBinding) error {
	record := r.records[binding.ID]
	if err := binding.Validate(r.Session); err != nil {
		return err
	}
	if record == nil || record.State == ActorRemoved || binding.Generation != record.Identity.Generation {
		return errors.New("unknown actor or stale native binding")
	}
	key := binding.Participant + ":" + binding.NativeID
	if owner := r.native[key]; owner != "" && owner != binding.ID {
		return fmt.Errorf("native unit %s already bound to %s", key, owner)
	}
	if old, exists := record.Bindings[binding.Participant]; exists && old != binding {
		return errors.New("conflicting native binding")
	}
	record.Bindings[binding.Participant] = binding
	r.native[key] = binding.ID
	if len(record.Bindings) == 2 {
		record.State = ActorActive
	}
	return nil
}

func (r *ActorRegistry) Despawn(event ActorDespawn) error {
	record := r.records[event.ID]
	if err := event.Validate(r.Session); err != nil {
		return err
	}
	if record == nil || event.Generation != record.Identity.Generation {
		return errors.New("unknown actor or stale despawn")
	}
	if record.State == ActorRemoved {
		return nil
	}
	for _, binding := range record.Bindings {
		delete(r.native, binding.Participant+":"+binding.NativeID)
	}
	record.Bindings = map[string]ActorBinding{}
	record.State = ActorRemoved
	return nil
}

func (r *ActorRegistry) Lookup(id string) (ActorRecord, bool) {
	record := r.records[id]
	if record == nil {
		return ActorRecord{}, false
	}
	copy := *record
	copy.Bindings = make(map[string]ActorBinding, len(record.Bindings))
	for role, binding := range record.Bindings {
		copy.Bindings[role] = binding
	}
	return copy, true
}

func (r *ActorRegistry) Living() []ActorIdentity {
	ids := make([]string, 0, len(r.records))
	for id, record := range r.records {
		if record.State != ActorRemoved {
			ids = append(ids, id)
		}
	}
	sort.Strings(ids)
	living := make([]ActorIdentity, 0, len(ids))
	for _, id := range ids {
		living = append(living, r.records[id].Identity)
	}
	return living
}

func (r *ActorRegistry) Commandable(id string) bool {
	record := r.records[id]
	return record != nil && record.State == ActorActive
}

func (r *ActorRegistry) UnbindParticipant(participant string) {
	for _, record := range r.records {
		if binding, ok := record.Bindings[participant]; ok {
			delete(r.native, participant+":"+binding.NativeID)
			delete(record.Bindings, participant)
			if record.State != ActorRemoved {
				record.State = ActorSpawning
			}
		}
	}
}

// Reconcile replays the authoritative living set after a bridge restart or
// publisher reconnect. Missing actors are removed; existing bindings survive.
// Tombstones remain until a new simulation session is explicitly started.
func (r *ActorRegistry) Reconcile(session string, living []ActorIdentity) error {
	if session != r.Session {
		return errors.New("stale actor session")
	}
	seen := map[string]bool{}
	for _, identity := range living {
		if seen[identity.ID] {
			return errors.New("duplicate actor in reconciliation")
		}
		seen[identity.ID] = true
		if err := identity.Validate(session); err != nil {
			return err
		}
		if prior := r.records[identity.ID]; prior != nil &&
			(prior.Identity != identity || prior.State == ActorRemoved) {
			return errors.New("actor ID already used")
		}
	}
	for _, identity := range living {
		if err := r.Spawn(identity); err != nil {
			return err
		}
	}
	ids := make([]string, 0, len(r.records))
	for id := range r.records {
		ids = append(ids, id)
	}
	sort.Strings(ids)
	for _, id := range ids {
		if !seen[id] && r.records[id].State != ActorRemoved {
			identity := r.records[id].Identity
			if err := r.Despawn(ActorDespawn{ID: id, Session: session, Generation: identity.Generation}); err != nil {
				return err
			}
		}
	}
	return nil
}
