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
	Session            string            `json:"session"`
	DefinitionHash     string            `json:"definition_hash"`
	ObjectiveEntityID  string            `json:"objective_entity_id,omitempty"`
	ObjectiveDestroyed bool              `json:"objective_destroyed,omitempty"`
	ObjectiveRemoved   bool              `json:"objective_removed,omitempty"`
	StartFrame         int               `json:"start_frame"`
	Started            bool              `json:"started"`
	LastFrame          int               `json:"last_frame"`
	LastSeq            uint64            `json:"last_seq"`
	NextAutomaticFrame int               `json:"next_automatic_frame,omitempty"`
	DefenseEnabled     bool              `json:"defense_enabled,omitempty"`
	SpawnAnchor        *[2]int           `json:"spawn_anchor,omitempty"`
	FixedSpawnZone     SpawnZone         `json:"fixed_spawn_zone,omitempty"`
	NextWaveSequence   int               `json:"next_wave_sequence,omitempty"`
	TotalTriggered     int               `json:"total_triggered,omitempty"`
	LastManualFrame    int               `json:"last_manual_frame,omitempty"`
	ManualRequests     map[string]string `json:"manual_requests,omitempty"`
	ManualOrder        []string          `json:"manual_order,omitempty"`
	ManualSequence     map[int]int       `json:"manual_sequence,omitempty"`
	Waves              []RuntimeWave     `json:"waves"`
	Outcome            string            `json:"outcome,omitempty"`
	Error              string            `json:"error,omitempty"`
}
type RuntimeWave struct {
	ID             string          `json:"id"`
	TemplateID     string          `json:"template_id,omitempty"`
	Origin         string          `json:"origin,omitempty"`
	Sequence       int             `json:"sequence,omitempty"`
	SpawnZone      string          `json:"spawn_zone,omitempty"`
	FixedZone      SpawnZone       `json:"fixed_zone,omitempty"`
	Composition    []WaveTierGroup `json:"composition,omitempty"`
	State          string          `json:"state"`
	TriggeredFrame int             `json:"triggered_frame,omitempty"`
	Units          []RuntimeUnit   `json:"units,omitempty"`
	Submitted      int             `json:"submitted"`
	Shortfall      int             `json:"shortfall,omitempty"`
	FailureReason  string          `json:"failure_reason,omitempty"`
}
type RuntimeUnit struct {
	GroupIndex int              `json:"group_index"`
	UnitIndex  int              `json:"unit_index"`
	UnitType   string           `json:"unit_type,omitempty"`
	State      string           `json:"state"`
	ActorID    string           `json:"actor_id,omitempty"`
	Attempts   []RuntimeAttempt `json:"attempts,omitempty"`
}
type RuntimeAttempt struct {
	RequestID string `json:"request_id"`
	X         int    `json:"x"`
	Y         int    `json:"y"`
	Frame     int    `json:"frame,omitempty"`
	Reason    string `json:"reason,omitempty"`
}

func ScenarioDefinitionHash(s *Scenario) string {
	data, _ := json.Marshal(s)
	sum := sha256.Sum256(data)
	return hex.EncodeToString(sum[:])
}

func NewScenarioRuntime(s *Scenario, session string) *ScenarioRuntime {
	r := &ScenarioRuntime{Session: session, DefinitionHash: ScenarioDefinitionHash(s)}
	if s.Mode == "park_defense" {
		r.NextWaveSequence = 1
		return r
	}
	for _, wave := range s.Waves {
		r.Waves = append(r.Waves, RuntimeWave{ID: wave.ID, State: "pending"})
	}
	return r
}

func (r *ScenarioRuntime) Validate(s *Scenario, session string) error {
	if r.Session != session || r.DefinitionHash != ScenarioDefinitionHash(s) {
		return errors.New("scenario_session_or_hash_mismatch")
	}
	if s.Mode == "park_defense" {
		if r.NextWaveSequence < 1 || r.TotalTriggered < 0 {
			return errors.New("scenario_journal_sequence_invalid")
		}
		if s.ParkDefense.FixedSpawn {
			if r.DefenseEnabled && (r.SpawnAnchor == nil || len(r.FixedSpawnZone.Tiles) == 0 || r.NextAutomaticFrame == 0) {
				return errors.New("scenario_journal_defense_invalid")
			}
			for _, tile := range r.FixedSpawnZone.Tiles {
				if !s.validTile(tile) {
					return errors.New("scenario_journal_spawn_zone_invalid")
				}
			}
		}
		for i := range r.Waves {
			wave := &r.Waves[i]
			if wave.TemplateID != "park-defense" || wave.Sequence < 1 ||
				(wave.Origin != "periodic" && wave.Origin != "manual") ||
				(!s.ParkDefense.FixedSpawn && s.SpawnZones[wave.SpawnZone].Tiles == nil) ||
				(s.ParkDefense.FixedSpawn && wave.SpawnZone != "selected") {
				return errors.New("scenario_journal_wave_mismatch")
			}
			if s.ParkDefense.FixedSpawn && len(wave.FixedZone.Tiles) == 0 {
				return errors.New("scenario_journal_wave_zone_missing")
			}
			groups := s.ParkDefense.GroupsForWave(wave.Sequence)
			if err := validateRuntimeUnits(*wave, groups, r.Session); err != nil {
				return err
			}
			normalizeLegacyWave(wave, groups)
		}
		return nil
	}
	if len(r.Waves) != len(s.Waves) {
		return errors.New("scenario_journal_wave_mismatch")
	}
	for i := range r.Waves {
		if r.Waves[i].ID != s.Waves[i].ID {
			return errors.New("scenario_journal_wave_mismatch")
		}
		groups := make([]WaveTierGroup, 0, len(s.Waves[i].Groups))
		for _, group := range s.Waves[i].Groups {
			groups = append(groups, WaveTierGroup{UnitType: group.UnitType, Count: group.Count})
		}
		if err := validateRuntimeUnits(r.Waves[i], groups, r.Session); err != nil {
			return err
		}
		normalizeLegacyWave(&r.Waves[i], groups)
	}
	return nil
}

// ValidateSpawnQueue rejects a persisted queue entry that would recreate a
// different unit or location for a durable scenario intent.
func (r *ScenarioRuntime) ValidateSpawnQueue(queue *SpawnQueue) error {
	if queue == nil {
		return nil
	}
	for _, wave := range r.Waves {
		for _, unit := range wave.Units {
			for _, attempt := range unit.Attempts {
				request, ok := queue.Request(attempt.RequestID)
				if !ok {
					continue // journal-first intent may not yet have reached the queue
				}
				if request.UnitType != unit.UnitType || request.X != attempt.X || request.Y != attempt.Y ||
					request.Count != 1 || request.PlayerID != 0 || request.Formation != "compact" {
					return fmt.Errorf("scenario_spawn_journal_mismatch: %s", attempt.RequestID)
				}
			}
		}
	}
	return nil
}

func normalizeLegacyWave(wave *RuntimeWave, groups []WaveTierGroup) {
	if len(wave.Composition) == 0 && len(wave.Units) > 0 {
		wave.Composition = append([]WaveTierGroup(nil), groups...)
	}
	for i := range wave.Units {
		if wave.Units[i].UnitType == "" {
			wave.Units[i].UnitType = groups[wave.Units[i].GroupIndex].UnitType
		}
	}
}

func validateRuntimeUnits(wave RuntimeWave, groups []WaveTierGroup, session string) error {
	expectedCount := 0
	for _, group := range groups {
		expectedCount += group.Count
	}
	if wave.State != "pending" && len(wave.Units) != expectedCount || wave.State == "pending" && len(wave.Units) != 0 {
		return errors.New("scenario_journal_unit_count_mismatch")
	}
	if len(wave.Composition) > 0 {
		if len(wave.Composition) != len(groups) {
			return errors.New("scenario_journal_composition_mismatch")
		}
		for i := range groups {
			if wave.Composition[i] != groups[i] {
				return errors.New("scenario_journal_composition_mismatch")
			}
		}
	} else if len(wave.Units) > 0 {
		// Old journals were exclusively Zergling. A missing composition in a
		// mixed scenario cannot be reconstructed without changing intent.
		for _, group := range groups {
			if group.UnitType != "zerg_zergling" {
				return errors.New("scenario_journal_composition_missing")
			}
		}
	}
	seen := map[[2]int]bool{}
	for _, unit := range wave.Units {
		if unit.GroupIndex < 0 || unit.GroupIndex >= len(groups) || unit.UnitIndex < 0 || unit.UnitIndex >= groups[unit.GroupIndex].Count {
			return errors.New("scenario_journal_unit_mismatch")
		}
		key := [2]int{unit.GroupIndex, unit.UnitIndex}
		if seen[key] {
			return errors.New("scenario_journal_unit_duplicate")
		}
		seen[key] = true
		want := groups[unit.GroupIndex].UnitType
		if unit.UnitType != "" && unit.UnitType != want || unit.UnitType == "" && want != "zerg_zergling" {
			return errors.New("scenario_journal_unit_type_mismatch")
		}
		for index, attempt := range unit.Attempts {
			if attempt.RequestID != runtimeRequestID(wave.ID, unit.GroupIndex, unit.UnitIndex, index, session) {
				return errors.New("scenario_journal_request_identity_mismatch")
			}
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
	if s.Mode == "park_defense" {
		if s.ParkDefense.ManualActivation && !r.DefenseEnabled {
			return false
		}
		if r.NextAutomaticFrame == 0 {
			r.NextAutomaticFrame = r.StartFrame + s.ParkDefense.InitialDelayFrames
			return true
		}
		if r.LastFrame < r.NextAutomaticFrame {
			return false
		}
		for _, wave := range r.Waves {
			if wave.Origin == "periodic" && (wave.State == "triggered" || wave.State == "spawning") {
				// Keep one scheduled intent while capacity or construction is blocked.
				return false
			}
		}
		r.newParkDefenseWave(s, "periodic")
		// A late complete frame creates one attack, with no outage burst.
		r.NextAutomaticFrame = r.LastFrame + s.ParkDefense.IntervalFrames
		return true
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
			entry.Composition = append(entry.Composition, WaveTierGroup{UnitType: group.UnitType, Count: group.Count})
			for ui := 0; ui < group.Count; ui++ {
				entry.Units = append(entry.Units, RuntimeUnit{GroupIndex: gi, UnitIndex: ui, UnitType: group.UnitType, State: "planned"})
			}
		}
		changed = true
	}
	return changed
}

func (r *ScenarioRuntime) newParkDefenseWave(s *Scenario, origin string) string {
	sequence := r.NextWaveSequence
	r.NextWaveSequence++
	r.TotalTriggered++
	id := fmt.Sprintf("%s-%04d", origin, sequence)
	zone := "selected"
	if !s.ParkDefense.FixedSpawn {
		zone = s.ParkDefense.SpawnZones[(sequence-1)%len(s.ParkDefense.SpawnZones)]
	}
	wave := RuntimeWave{ID: id, TemplateID: "park-defense", Origin: origin,
		Sequence: sequence, SpawnZone: zone, State: "triggered", TriggeredFrame: r.LastFrame}
	if s.ParkDefense.FixedSpawn {
		wave.FixedZone = SpawnZone{Tiles: append([][2]int(nil), r.FixedSpawnZone.Tiles...)}
	}
	for gi, group := range s.ParkDefense.GroupsForWave(sequence) {
		wave.Composition = append(wave.Composition, group)
		for index := 0; index < group.Count; index++ {
			wave.Units = append(wave.Units, RuntimeUnit{GroupIndex: gi, UnitIndex: index, UnitType: group.UnitType, State: "planned"})
		}
	}
	r.Waves = append(r.Waves, wave)
	return id
}

// RequestManual records one durable extra wave without changing the automatic
// deadline. Replays return the original wave; older evicted IDs are rejected.
func (r *ScenarioRuntime) RequestManual(s *Scenario, requestID string, playerID, requestSequence int) (string, error) {
	if s.Mode != "park_defense" || !r.Started || r.Outcome != "" || r.Error != "" {
		return "", errors.New("scenario_not_ready")
	}
	if wave, ok := r.ManualRequests[requestID]; ok {
		return wave, nil
	}
	if s.ParkDefense.ManualActivation && !r.DefenseEnabled {
		return "", errors.New("defense_disabled")
	}
	if requestID == "" || len(requestID) > 128 {
		return "", errors.New("invalid_wave_request")
	}
	if playerID < 0 || requestSequence < 1 || requestSequence <= r.ManualSequence[playerID] {
		return "", errors.New("stale_wave_request")
	}
	if r.LastManualFrame > 0 && r.LastFrame-r.LastManualFrame < s.ParkDefense.ManualCooldownFrames {
		return "", errors.New("manual_wave_cooldown")
	}
	id := r.newParkDefenseWave(s, "manual")
	r.LastManualFrame = r.LastFrame
	if r.ManualRequests == nil {
		r.ManualRequests = make(map[string]string)
	}
	r.ManualRequests[requestID] = id
	if r.ManualSequence == nil {
		r.ManualSequence = make(map[int]int)
	}
	r.ManualSequence[playerID] = requestSequence
	r.ManualOrder = append(r.ManualOrder, requestID)
	if len(r.ManualOrder) > 128 {
		delete(r.ManualRequests, r.ManualOrder[0])
		r.ManualOrder = r.ManualOrder[1:]
	}
	return id, nil
}

// WaveZone resolves an instance against its recorded template rather than its
// position in the authored finite-wave list.
func (r *ScenarioRuntime) WaveZone(s *Scenario, wi, group int) (SpawnZone, bool) {
	if wi < 0 || wi >= len(r.Waves) {
		return SpawnZone{}, false
	}
	instance := r.Waves[wi]
	if s.Mode == "park_defense" {
		zone, ok := s.SpawnZones[instance.SpawnZone]
		if s.ParkDefense.FixedSpawn {
			zone, ok = instance.FixedZone, len(instance.FixedZone.Tiles) > 0
		}
		groups := instance.Composition
		if len(groups) == 0 {
			groups = s.ParkDefense.GroupsForWave(instance.Sequence) // validated Zergling-only legacy journal
		}
		return zone, ok && group >= 0 && group < len(groups)
	}
	if wi >= len(s.Waves) || group < 0 || group >= len(s.Waves[wi].Groups) {
		return SpawnZone{}, false
	}
	zone, ok := s.SpawnZones[s.Waves[wi].Groups[group].SpawnZone]
	return zone, ok
}

// WaveZones tries the wave's rotating zone first, then the other authored
// zones. The primary is recorded in the durable wave for restart stability.
func (r *ScenarioRuntime) WaveZones(s *Scenario, wi, group int) ([]SpawnZone, bool) {
	primary, ok := r.WaveZone(s, wi, group)
	if !ok {
		return nil, false
	}
	zones := []SpawnZone{primary}
	if s.Mode == "park_defense" && !s.ParkDefense.FixedSpawn {
		for _, id := range s.ParkDefense.SpawnZones {
			if id != r.Waves[wi].SpawnZone {
				zones = append(zones, s.SpawnZones[id])
			}
		}
	}
	return zones, true
}

// PruneParkDefenseHistory retains recent completed attacks and all work that
// may still need native reconciliation. The caller saves the runtime before
// removing corresponding settled queue entries.
func (r *ScenarioRuntime) PruneParkDefenseHistory(s *Scenario) []string {
	if s.Mode != "park_defense" || len(r.Waves) <= 64 {
		return nil
	}
	completed := 0
	for _, wave := range r.Waves {
		if wave.State == "cleared" || wave.State == "failed" {
			completed++
		}
	}
	remove := completed - 64
	if remove <= 0 {
		return nil
	}
	requests := []string{}
	kept := make([]RuntimeWave, 0, len(r.Waves)-remove)
	for _, wave := range r.Waves {
		if remove > 0 && (wave.State == "cleared" || wave.State == "failed") {
			for _, unit := range wave.Units {
				for _, attempt := range unit.Attempts {
					requests = append(requests, attempt.RequestID)
				}
			}
			remove--
			continue
		}
		kept = append(kept, wave)
	}
	r.Waves = kept
	return requests
}

// NextPlanned returns one unit that needs initial placement or a confirmed
// placement retry. A pending native request is never replaced speculatively.
func (r *ScenarioRuntime) NextPlanned() (int, int, bool) {
	return r.NextPlannedExcept(nil)
}

// NextPlannedExcept lets one dispatch pass defer unavailable zones while
// trying other durable wave instances. Every deferred unit is retried on the
// next complete native frame.
func (r *ScenarioRuntime) NextPlannedExcept(excluded map[[2]int]bool) (int, int, bool) {
	if r.Outcome != "" || r.Error != "" {
		return 0, 0, false
	}
	for wi := range r.Waves {
		wave := &r.Waves[wi]
		if wave.State != "triggered" && wave.State != "spawning" {
			continue
		}
		for ui := range wave.Units {
			if wave.Units[ui].State == "planned" && !excluded[[2]int{wi, ui}] {
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
	id := runtimeRequestID(wave.ID, unit.GroupIndex, unit.UnitIndex, attempt, r.Session)
	unit.Attempts = append(unit.Attempts, RuntimeAttempt{RequestID: id, X: position.X, Y: position.Y, Frame: r.LastFrame})
	unit.State, wave.State = "submitted", "spawning"
	wave.Submitted++
	unitType := unit.UnitType
	if unitType == "" {
		unitType = "zerg_zergling"
	} // validated legacy journal
	return SpawnRequest{RequestID: id, UnitType: unitType, Count: 1,
		X: position.X, Y: position.Y, Formation: "compact", PlayerID: 0}
}

func runtimeRequestID(wave string, group, unit, attempt int, session string) string {
	key := fmt.Sprintf("%s/%s/%d/%d/%d", session, wave, group, unit, attempt)
	sum := sha256.Sum256([]byte(key))
	return "scenario:" + hex.EncodeToString(sum[:16])
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
	return reason == "invalid_or_occupied_native_position" || reason == "invalid_native_position" ||
		reason == "native_unwalkable_position" || reason == "occupied"
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
