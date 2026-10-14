package world

import (
	"encoding/json"
	"errors"
	"fmt"
	"regexp"
	"sort"
)

const Version = 1

var identifier = regexp.MustCompile(`^[a-zA-Z0-9_.:/#-]{1,128}$`)

type Point struct {
	X int `json:"x"`
	Y int `json:"y"`
}
type Rect struct {
	X      int `json:"x"`
	Y      int `json:"y"`
	Width  int `json:"width"`
	Height int `json:"height"`
}
type Geometry struct {
	Cells []Point `json:"cells,omitempty"`
	Rects []Rect  `json:"rects,omitempty"`
}
type Collision struct {
	Blocks bool `json:"blocks"`
}
type Combat struct {
	Targetable  bool    `json:"targetable"`
	Health      int     `json:"health"`
	Armor       int     `json:"armor,omitempty"`
	DamageScale float64 `json:"damage_scale,omitempty"`
}
type Removal struct {
	Action string         `json:"action"`
	Args   map[string]int `json:"args,omitempty"`
	Effect string         `json:"effect,omitempty"`
}
type Entity struct {
	ID           string    `json:"id"`
	Name         string    `json:"name,omitempty"`
	Source       string    `json:"source"`
	SourceID     string    `json:"source_id"`
	Kind         string    `json:"kind"`
	Type         string    `json:"type"`
	Owner        int       `json:"owner"`
	Position     Point     `json:"position"`
	Rotation     int       `json:"rotation,omitempty"`
	Elevation    int       `json:"elevation"`
	Geometry     Geometry  `json:"geometry"`
	Collision    Collision `json:"collision"`
	Destructible bool      `json:"destructible"`
	Combat       Combat    `json:"combat"`
	Removal      Removal   `json:"removal"`
	Revision     uint64    `json:"revision"`
}
type Terrain struct {
	X           int           `json:"x"`
	Y           int           `json:"y"`
	Height      int           `json:"height"` // OpenRCT2 world Z units (8 per baseHeight step)
	Slope       int           `json:"slope,omitempty"`
	Water       int           `json:"water"`
	Surface     int           `json:"surface"`
	Walkable    bool          `json:"walkable"`
	GroundPaths []TerrainPath `json:"ground_paths,omitempty"`
}
type TerrainPath struct {
	BaseHeight     int  `json:"base_height"`     // OpenRCT2 world Z units
	SlopeDirection *int `json:"slope_direction"` // null means a flat path
}
type SnapshotChunk struct {
	Index    int       `json:"index"`
	Entities []Entity  `json:"entities,omitempty"`
	Terrain  []Terrain `json:"terrain,omitempty"`
}
type SnapshotBegin struct {
	Width       int    `json:"width"`
	Height      int    `json:"height"`
	Chunks      int    `json:"chunks"`
	ObjectiveID string `json:"objective_id,omitempty"`
}
type SnapshotEnd struct {
	Entities int `json:"entities"`
	Terrain  int `json:"terrain"`
}
type Envelope struct {
	V        int             `json:"v"`
	Kind     string          `json:"kind"`
	Session  string          `json:"session"`
	OpID     string          `json:"op_id"`
	Source   string          `json:"source"`
	Revision uint64          `json:"revision"`
	BWTick   int             `json:"bw_tick,omitempty"`
	Payload  json.RawMessage `json:"payload"`
}
type Ack struct {
	OpID     string `json:"op_id"`
	Accepted bool   `json:"accepted"`
	Error    string `json:"error,omitempty"`
}
type Ready struct {
	Entities           int            `json:"entities"`
	Targets            int            `json:"targets"`
	Marines            int            `json:"marines,omitempty"`
	Zerglings          int            `json:"zerglings,omitempty"`
	Obstacles          int            `json:"obstacles,omitempty"`
	Navigation         string         `json:"navigation,omitempty"`
	Resuming           bool           `json:"resuming,omitempty"`
	Reconciled         *bool          `json:"reconciled,omitempty"`
	TargetCapacity     int            `json:"target_capacity,omitempty"`
	TargetIDs          []string       `json:"target_ids,omitempty"`
	Unsupported        []string       `json:"unsupported,omitempty"`
	UnsupportedTotal   int            `json:"unsupported_total,omitempty"`
	UnsupportedReasons map[string]int `json:"unsupported_reasons,omitempty"`
}
type CombatEvent struct {
	ID       string `json:"id"`
	EntityID string `json:"entity_id"`
	ProxyID  string `json:"proxy_id"`
	Type     string `json:"type"`
	Health   int    `json:"health"`
}
type CombatResult struct {
	EventID  string `json:"event_id"`
	EntityID string `json:"entity_id"`
	State    string `json:"state"`
	Reason   string `json:"reason,omitempty"`
}

func Message(kind, session, opID, source string, revision uint64, payload any) Envelope {
	b, _ := json.Marshal(payload)
	return Envelope{Version, kind, session, opID, source, revision, 0, b}
}
func (m Envelope) Decode(v any) error { return json.Unmarshal(m.Payload, v) }
func (m Envelope) Validate() error {
	if m.V != Version {
		return fmt.Errorf("unsupported world protocol %d", m.V)
	}
	if !identifier.MatchString(m.Session) || !identifier.MatchString(m.OpID) {
		return errors.New("invalid session or operation ID")
	}
	if m.Source != "openrct2" && m.Source != "openbw" && m.Source != "bridge" {
		return errors.New("invalid authority")
	}
	if m.Revision == 0 || len(m.Payload) == 0 || len(m.Payload) > 1048576 {
		return errors.New("invalid revision or payload")
	}
	if m.Kind == "actor.spawn" || m.Kind == "actor.bind" || m.Kind == "actor.despawn" || m.Kind == "actor.reconcile" {
		if m.Source != "openbw" {
			return errors.New("invalid actor authority")
		}
		switch m.Kind {
		case "actor.spawn":
			var identity ActorIdentity
			if err := decodeActorPayload(m.Payload, &identity); err != nil {
				return err
			}
			return identity.Validate(m.Session)
		case "actor.bind":
			var binding ActorBinding
			if err := decodeActorPayload(m.Payload, &binding); err != nil {
				return err
			}
			return binding.Validate(m.Session)
		case "actor.despawn":
			var event ActorDespawn
			if err := decodeActorPayload(m.Payload, &event); err != nil {
				return err
			}
			return event.Validate(m.Session)
		case "actor.reconcile":
			var state ActorReconcile
			if err := decodeActorPayload(m.Payload, &state); err != nil {
				return err
			}
			if len(state.Living) > 4096 {
				return errors.New("actor reconciliation exceeds limit")
			}
			seen := map[string]bool{}
			for _, identity := range state.Living {
				if err := identity.Validate(m.Session); err != nil {
					return err
				}
				if seen[identity.ID] {
					return errors.New("duplicate reconciled actor")
				}
				seen[identity.ID] = true
			}
		}
	}
	switch m.Kind {
	case "unit.spawn.request", "unit.spawn.query", "unit.spawn.cancel":
		if m.Source != "openrct2" {
			return errors.New("invalid spawn request authority")
		}
		if m.Kind == "unit.spawn.request" {
			var request SpawnRequest
			return decodeActorPayload(m.Payload, &request)
		}
		var query struct {
			RequestID string `json:"request_id"`
		}
		return decodeActorPayload(m.Payload, &query)
	case "unit.spawn.execute":
		if m.Source != "bridge" {
			return errors.New("invalid spawn execution authority")
		}
		var execute SpawnExecute
		return decodeActorPayload(m.Payload, &execute)
	case "unit.spawn.reconcile":
		if m.Source != "bridge" {
			return errors.New("invalid spawn reconciliation authority")
		}
	case "unit.spawn.status":
		if m.Source != "openbw" && m.Source != "bridge" {
			return errors.New("invalid spawn status authority")
		}
	}
	return nil
}
func (e Entity) Validate(width, height int) error {
	if !identifier.MatchString(e.ID) || !identifier.MatchString(e.SourceID) || (e.Source != "openrct2" && e.Source != "openbw") || !identifier.MatchString(e.Kind) || e.Type == "" || e.Revision == 0 {
		return errors.New("invalid entity identity")
	}
	if e.Position.X < 0 || e.Position.Y < 0 || e.Position.X >= width*32 || e.Position.Y >= height*32 || e.Rotation < 0 || e.Rotation > 255 || e.Elevation < -4096 || e.Elevation > 32768 {
		return errors.New("entity outside world")
	}
	if len(e.Geometry.Cells) > 16384 || len(e.Geometry.Rects) > 16384 {
		return errors.New("geometry exceeds limit")
	}
	for _, c := range e.Geometry.Cells {
		if c.X < 0 || c.Y < 0 || c.X >= width || c.Y >= height {
			return errors.New("cell outside world")
		}
	}
	for _, r := range e.Geometry.Rects {
		if r.X < 0 || r.Y < 0 || r.Width <= 0 || r.Height <= 0 || r.X+r.Width > width*32 || r.Y+r.Height > height*32 {
			return errors.New("rectangle outside world")
		}
	}
	if e.Combat.Health < 0 || e.Combat.Health > 100000 || e.Combat.Armor < 0 || e.Combat.Armor > 255 {
		return errors.New("invalid combat values")
	}
	if e.Combat.DamageScale < 0 || e.Combat.DamageScale > 100 {
		return errors.New("invalid damage scale")
	}
	if e.Kind == "terrain" && e.Destructible {
		return errors.New("terrain cannot be destructible")
	}
	return nil
}

// Registry replaces its derived state atomically when the complete authoritative
// snapshot has passed validation. A rebuilt object at the same tile uses a new ID.
type Registry struct {
	Session      string
	Revision     uint64
	Width        int
	Height       int
	Entities     map[string]Entity
	Terrain      []Terrain
	Destroyed    map[string]bool
	RemovalState map[string]string
	Seen         map[string]Ack
}

func cloneEntity(e Entity) Entity {
	e.Geometry.Cells = append([]Point(nil), e.Geometry.Cells...)
	e.Geometry.Rects = append([]Rect(nil), e.Geometry.Rects...)
	if e.Removal.Args != nil {
		args := make(map[string]int, len(e.Removal.Args))
		for k, v := range e.Removal.Args {
			args[k] = v
		}
		e.Removal.Args = args
	}
	return e
}

func NewRegistry() *Registry {
	return &Registry{Entities: map[string]Entity{}, Destroyed: map[string]bool{}, RemovalState: map[string]string{}, Seen: map[string]Ack{}}
}
func (r *Registry) Replace(session string, revision uint64, width, height int, entities []Entity, terrain []Terrain) error {
	if width < 1 || height < 1 || width > 1024 || height > 1024 || len(entities) > 200000 || len(terrain) > width*height {
		return errors.New("invalid snapshot dimensions")
	}
	next := make(map[string]Entity, len(entities))
	for _, e := range entities {
		if e.Source != "openrct2" {
			return errors.New("park snapshot contains non-park entity")
		}
		if err := e.Validate(width, height); err != nil {
			return fmt.Errorf("%s: %w", e.ID, err)
		}
		if _, exists := next[e.ID]; exists {
			return fmt.Errorf("duplicate entity %s", e.ID)
		}
		next[e.ID] = cloneEntity(e)
	}
	seenCells := map[Point]bool{}
	for _, t := range terrain {
		p := Point{t.X, t.Y}
		if t.X < 0 || t.Y < 0 || t.X >= width || t.Y >= height || seenCells[p] {
			return errors.New("invalid or duplicate terrain cell")
		}
		if err := t.ValidateGeometry(); err != nil {
			return fmt.Errorf("unsupported_terrain at %d,%d: %w", t.X, t.Y, err)
		}
		seenCells[p] = true
	}
	r.Session, r.Revision, r.Width, r.Height = session, revision, width, height
	r.Entities, r.Terrain, r.Destroyed, r.RemovalState, r.Seen = next, terrain, map[string]bool{}, map[string]string{}, map[string]Ack{}
	return nil
}
func (r *Registry) IDs() []string {
	ids := make([]string, 0, len(r.Entities))
	for id := range r.Entities {
		ids = append(ids, id)
	}
	sort.Strings(ids)
	return ids
}
func (r *Registry) Apply(m Envelope) Ack {
	if old, ok := r.Seen[m.OpID]; ok {
		return old
	}
	a := Ack{OpID: m.OpID}
	defer func() { r.Seen[m.OpID] = a }()
	if m.Session != r.Session {
		a.Error = "stale_session"
		return a
	}
	if m.Revision != r.Revision+1 {
		a.Error = "out_of_order_revision"
		return a
	}
	if m.Source != "openrct2" {
		a.Error = "wrong_authority"
		return a
	}
	switch m.Kind {
	case "entity.upsert", "entity.transform", "entity.state":
		var e Entity
		if m.Decode(&e) != nil || e.Validate(r.Width, r.Height) != nil || e.Revision != m.Revision {
			a.Error = "invalid_entity"
			return a
		}
		if previous, ok := r.Entities[e.ID]; ok && (previous.SourceID != e.SourceID || previous.Kind != e.Kind) {
			a.Error = "identity_changed"
			return a
		}
		r.Entities[e.ID] = cloneEntity(e)
	case "entity.remove":
		var p struct {
			ID string `json:"id"`
		}
		if m.Decode(&p) != nil || r.Entities[p.ID].ID == "" {
			a.Error = "unknown_entity"
			return a
		}
		delete(r.Entities, p.ID)
		r.Destroyed[p.ID] = true
	case "navigation.terrain.update":
		var p Terrain
		if m.Decode(&p) != nil || p.X < 0 || p.Y < 0 || p.X >= r.Width || p.Y >= r.Height || p.ValidateGeometry() != nil {
			a.Error = "invalid_terrain"
			return a
		}
		for i := range r.Terrain {
			if r.Terrain[i].X == p.X && r.Terrain[i].Y == p.Y {
				r.Terrain[i] = p
				a.Accepted = true
				r.Revision = m.Revision
				return a
			}
		}
		r.Terrain = append(r.Terrain, p)
	default:
		a.Error = "unsupported_operation"
		return a
	}
	r.Revision = m.Revision
	a.Accepted = true
	return a
}
