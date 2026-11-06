package world

import (
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"reflect"
)

// ConstructionIntent is a durable request, not an instruction to replay an
// uncertain native order. Tile is the upper-left OpenRCT2 tile.
type ConstructionIntent struct {
	ID                 string `json:"id"`
	WorkerID           string `json:"worker_id"`
	BuildingType       string `json:"building_type"`
	Tile               Point  `json:"tile"`
	GeyserSiteID       string `json:"geyser_site_id,omitempty"`
	GeyserGeneration   uint64 `json:"geyser_generation,omitempty"`
	GeyserNativeID     string `json:"geyser_native_id,omitempty"`
	GeyserControllerID string `json:"geyser_controller_id,omitempty"`
	State              string `json:"state"`
	NativeID           string `json:"native_id,omitempty"`
	ControllerNativeID string `json:"controller_native_id,omitempty"`
	NativeGeneration   uint64 `json:"native_generation,omitempty"`
	ProjectionID       string `json:"projection_id,omitempty"`
	CancelRequested    bool   `json:"cancel_requested,omitempty"`
	ProjectionFailures int    `json:"projection_failures,omitempty"`
	ProjectionError    string `json:"projection_error,omitempty"`
}

type ConstructionObservation struct {
	IntentID           string
	NativeID           string
	ControllerNativeID string
	Type               string
	Owner              int
	Tile               Point
	Generation         uint64
}

type ConstructionLedger struct {
	Session string                        `json:"session"`
	Intents map[string]ConstructionIntent `json:"intents"`
	DestroyedAuthored map[string]bool     `json:"destroyed_authored,omitempty"`
	path    string
}

func LoadConstructionLedger(path, session string) (*ConstructionLedger, error) {
	if path == "" || session == "" {
		return nil, errors.New("missing_construction_journal")
	}
	l := &ConstructionLedger{Session: session, Intents: map[string]ConstructionIntent{},
		DestroyedAuthored: map[string]bool{}, path: path}
	data, err := os.ReadFile(path)
	if errors.Is(err, os.ErrNotExist) {
		return l, nil
	}
	if err != nil {
		return nil, err
	}
	if err := json.Unmarshal(data, l); err != nil {
		return nil, err
	}
	if l.Session != session {
		return nil, errors.New("construction_session_mismatch")
	}
	if l.Intents == nil {
		return nil, errors.New("invalid_construction_journal")
	}
	if l.DestroyedAuthored == nil {
		l.DestroyedAuthored = map[string]bool{}
	}
	l.path = path
	return l, nil
}

func (l *ConstructionLedger) MarkAuthoredDestroyed(id string) error {
	if !identifier.MatchString(id) {
		return errors.New("invalid_authored_construction_id")
	}
	if l.DestroyedAuthored[id] {
		return nil
	}
	l.DestroyedAuthored[id] = true
	if err := l.save(); err != nil {
		delete(l.DestroyedAuthored, id)
		return err
	}
	return nil
}

func (l *ConstructionLedger) save() error {
	if err := os.MkdirAll(filepath.Dir(l.path), 0700); err != nil {
		return err
	}
	data, err := json.MarshalIndent(l, "", "  ")
	if err != nil {
		return err
	}
	tmp := l.path + ".tmp"
	f, err := os.OpenFile(tmp, os.O_CREATE|os.O_TRUNC|os.O_WRONLY, 0600)
	if err != nil {
		return err
	}
	if _, err = f.Write(data); err == nil {
		err = f.Sync()
	}
	closeErr := f.Close()
	if err != nil {
		return err
	}
	if closeErr != nil {
		return closeErr
	}
	if err := os.Rename(tmp, l.path); err != nil {
		return err
	}
	dir, err := os.Open(filepath.Dir(l.path))
	if err != nil {
		return err
	}
	defer dir.Close()
	return dir.Sync()
}

func (l *ConstructionLedger) update(intent ConstructionIntent) error {
	before, exists := l.Intents[intent.ID]
	l.Intents[intent.ID] = intent
	if err := l.save(); err != nil {
		if exists {
			l.Intents[intent.ID] = before
		} else {
			delete(l.Intents, intent.ID)
		}
		return err
	}
	return nil
}

func constructionRect(intent ConstructionIntent) Rect {
	building, _ := SupportedBuilding(intent.BuildingType)
	return Rect{X: intent.Tile.X * 32, Y: intent.Tile.Y * 32,
		Width: building.Width * 32, Height: building.Height * 32}
}

func rectanglesOverlap(a, b Rect) bool {
	return a.X < b.X+b.Width && b.X < a.X+a.Width &&
		a.Y < b.Y+b.Height && b.Y < a.Y+a.Height
}

func (l *ConstructionLedger) Reserve(intent ConstructionIntent, width, height int) error {
	if old, ok := l.Intents[intent.ID]; ok {
		intent.State, intent.NativeID, intent.ControllerNativeID, intent.NativeGeneration, intent.ProjectionID, intent.CancelRequested, intent.ProjectionFailures, intent.ProjectionError =
			old.State, old.NativeID, old.ControllerNativeID, old.NativeGeneration, old.ProjectionID, old.CancelRequested, old.ProjectionFailures, old.ProjectionError
		if reflect.DeepEqual(old, intent) {
			return nil
		}
		return errors.New("conflicting_construction_request")
	}
	building, ok := SupportedBuilding(intent.BuildingType)
	if !ok || len(intent.BuildingType) < 8 || intent.BuildingType[:7] != "terran_" ||
		!identifier.MatchString(intent.ID) || !unitIDPatternConstruction(intent.WorkerID) ||
		intent.Tile.X < 1 || intent.Tile.Y < 1 || intent.Tile.X+building.Width >= width ||
		intent.Tile.Y+building.Height >= height ||
		(intent.BuildingType == "terran_refinery") != (intent.GeyserSiteID != "") ||
		(intent.GeyserSiteID != "" && (intent.GeyserGeneration == 0 || intent.GeyserNativeID == "" || intent.GeyserControllerID == "")) {
		return errors.New("invalid_construction_intent")
	}
	for _, old := range l.Intents {
		if old.State != "rejected" && old.State != "canceled" && old.State != "destroyed" &&
			rectanglesOverlap(constructionRect(intent), constructionRect(old)) {
			return errors.New("construction_site_reserved")
		}
	}
	intent.State = "reserved"
	return l.update(intent)
}

func unitIDPatternConstruction(id string) bool {
	if len(id) < 8 || id[:7] != "openbw:" {
		return false
	}
	for _, c := range id[7:] {
		if c < '0' || c > '9' {
			return false
		}
	}
	return true
}

func (l *ConstructionLedger) MayDispatch(id string) bool { return l.Intents[id].State == "reserved" }

func (l *ConstructionLedger) MarkDispatched(id string) error {
	intent := l.Intents[id]
	if intent.State != "reserved" {
		return errors.New("construction_order_already_dispatched")
	}
	intent.State = "dispatched"
	return l.update(intent)
}

func (l *ConstructionLedger) Bind(observation ConstructionObservation) error {
	intent := l.Intents[observation.IntentID]
	if intent.ID == "" || (intent.State != "dispatched" && intent.State != "bound") ||
		observation.Owner != 1 || observation.NativeID == "" || observation.Generation == 0 ||
		observation.Type != intent.BuildingType || observation.Tile != intent.Tile ||
		(intent.GeyserSiteID != "" && (observation.NativeID != intent.GeyserNativeID ||
			observation.ControllerNativeID != intent.GeyserControllerID ||
			observation.Generation != intent.GeyserGeneration+1)) ||
		(intent.NativeID != "" && (intent.NativeID != observation.NativeID || intent.NativeGeneration != observation.Generation ||
			(intent.ControllerNativeID != "" && observation.ControllerNativeID != "" && intent.ControllerNativeID != observation.ControllerNativeID))) {
		return errors.New("construction_observation_mismatch")
	}
	for id, old := range l.Intents {
		if id != intent.ID && old.NativeID == observation.NativeID && old.State != "destroyed" && old.State != "canceled" {
			return errors.New("native_building_already_bound")
		}
	}
	intent.NativeID, intent.ControllerNativeID, intent.NativeGeneration, intent.State =
		observation.NativeID, observation.ControllerNativeID, observation.Generation, "bound"
	return l.update(intent)
}

func (l *ConstructionLedger) Complete(id, nativeID string) error {
	intent := l.Intents[id]
	if intent.State == "completed" && intent.NativeID == nativeID {
		return nil
	}
	if intent.State != "bound" || intent.NativeID != nativeID {
		return errors.New("construction_completion_mismatch")
	}
	intent.State = "completed"
	return l.update(intent)
}

func (l *ConstructionLedger) Terminal(id, state string) error {
	intent := l.Intents[id]
	if intent.ID == "" || (state != "rejected" && state != "canceled" && state != "destroyed") {
		return errors.New("invalid_construction_terminal_state")
	}
	if intent.State == state {
		return nil
	}
	if intent.State == "completed" && state != "destroyed" {
		return errors.New("completed_construction_cannot_cancel")
	}
	intent.State = state
	return l.update(intent)
}

func (l *ConstructionLedger) MarkCancelRequested(id string) error {
	intent := l.Intents[id]
	if intent.NativeID == "" || intent.State != "bound" {
		return errors.New("construction_not_cancelable")
	}
	if intent.CancelRequested {
		return nil
	}
	intent.CancelRequested = true
	return l.update(intent)
}

func (l *ConstructionLedger) ClearCancelRequested(id string) error {
	intent := l.Intents[id]
	if intent.ID == "" {
		return errors.New("unknown_construction")
	}
	if !intent.CancelRequested {
		return nil
	}
	intent.CancelRequested = false
	return l.update(intent)
}

func (l *ConstructionLedger) AllowProjection(id, entityID string) error {
	intent := l.Intents[id]
	if intent.NativeID == "" || (intent.State != "bound" && intent.State != "completed") ||
		!identifier.MatchString(entityID) || intent.ProjectionFailures >= 3 {
		return errors.New("construction_projection_unbound")
	}
	if intent.ProjectionID != "" && intent.ProjectionID != entityID {
		return errors.New("construction_projection_conflict")
	}
	intent.ProjectionID = entityID
	return l.update(intent)
}

func (l *ConstructionLedger) RecordProjectionFailure(id, reason string) error {
	intent := l.Intents[id]
	if intent.NativeID == "" || intent.ProjectionID != "" || len(reason) > 128 {
		return errors.New("invalid_projection_failure")
	}
	if intent.ProjectionFailures < 3 {
		intent.ProjectionFailures++
	}
	intent.ProjectionError = reason
	return l.update(intent)
}

func (l *ConstructionLedger) CheckGeyser(id string, state ResourceState) error {
	intent := l.Intents[id]
	if intent.BuildingType != "terran_refinery" || intent.GeyserSiteID != state.SiteID ||
		intent.GeyserGeneration != state.Generation || intent.GeyserNativeID != state.NativeID ||
		state.Type != "vespene_geyser" || state.Lifecycle != "deposit" {
		return errors.New("stale_geyser_binding")
	}
	return nil
}

// ValidateFinitePatch rejects a free military structure and any ordinary park
// edit that overlaps a native construction reservation. A bound projection is
// the only permitted structure addition at that site.
func (l *ConstructionLedger) ValidateFinitePatch(p Patch) error {
	for _, e := range append(append([]Entity{}, p.Additions...), p.Modifications...) {
		var permitted *ConstructionIntent
		for _, intent := range l.Intents {
			if intent.ProjectionID == e.ID && intent.NativeID != "" &&
				(intent.State == "bound" || intent.State == "completed") && intent.BuildingType == e.Type &&
				validProjectionGeometry(e, intent) {
				copy := intent
				permitted = &copy
				break
			}
		}
		if e.Kind == "structure" && len(e.Type) >= 7 && e.Type[:7] == "terran_" {
			if permitted == nil || e.Position.X/32 != permitted.Tile.X || e.Position.Y/32 != permitted.Tile.Y {
				return fmt.Errorf("free_economy_structure: %s", e.ID)
			}
		}
		for _, intent := range l.Intents {
			if intent.State == "rejected" || intent.State == "canceled" || intent.State == "destroyed" ||
				intent.ProjectionID == e.ID {
				continue
			}
			for _, rect := range e.Geometry.Rects {
				if rectanglesOverlap(rect, constructionRect(intent)) {
					return errors.New("construction_site_reserved")
				}
			}
			for _, cell := range e.Geometry.Cells {
				if rectanglesOverlap(Rect{X: cell.X * 32, Y: cell.Y * 32, Width: 32, Height: 32}, constructionRect(intent)) {
					return errors.New("construction_site_reserved")
				}
			}
		}
	}
	for _, id := range p.Removals {
		for _, intent := range l.Intents {
			if intent.ProjectionID == id && intent.State != "destroyed" && intent.State != "canceled" {
				return errors.New("native_construction_removal_requires_cancel")
			}
		}
	}
	for _, cell := range p.Terrain {
		for _, intent := range l.Intents {
			if intent.State != "rejected" && intent.State != "canceled" && intent.State != "destroyed" &&
				cell.X >= intent.Tile.X && cell.X < intent.Tile.X+constructionRect(intent).Width/32 &&
				cell.Y >= intent.Tile.Y && cell.Y < intent.Tile.Y+constructionRect(intent).Height/32 {
				return errors.New("construction_site_reserved")
			}
		}
	}
	return nil
}

func validProjectionGeometry(entity Entity, intent ConstructionIntent) bool {
	if entity.Kind != "structure" || entity.Owner != 1 ||
		entity.Position.X != intent.Tile.X*32 || entity.Position.Y != intent.Tile.Y*32 ||
		len(entity.Geometry.Cells) == 0 {
		return false
	}
	site := constructionRect(intent)
	inside := func(rect Rect) bool {
		return rect.Width > 0 && rect.Height > 0 && rect.X >= site.X && rect.Y >= site.Y &&
			rect.X+rect.Width <= site.X+site.Width && rect.Y+rect.Height <= site.Y+site.Height
	}
	for _, rect := range entity.Geometry.Rects {
		if !inside(rect) {
			return false
		}
	}
	for _, cell := range entity.Geometry.Cells {
		if !inside(Rect{X: cell.X * 32, Y: cell.Y * 32, Width: 32, Height: 32}) {
			return false
		}
	}
	return true
}

func (l *ConstructionLedger) NormalizeNativeProjection(entity *Entity) {
	if l == nil || entity == nil {
		return
	}
	entity.NativeOrigin = false
	entity.NativeID = ""
	for _, intent := range l.Intents {
		if intent.ProjectionID == entity.ID && intent.NativeID != "" &&
			(intent.State == "bound" || intent.State == "completed") &&
			intent.BuildingType == entity.Type && entity.Kind == "structure" {
			entity.NativeOrigin = true
			entity.NativeID = intent.NativeID
			entity.Collision.Blocks = false
			entity.Collision.Volumes = nil
			return
		}
	}
}

// ValidateConstructionSite checks park-owned, unobstructed ground before a
// native worker order. OpenBW still makes the final buildability decision,
// including exploration, unit occupancy, prerequisites and funds.
func ValidateConstructionSite(r *Registry, intent ConstructionIntent) error {
	building, ok := SupportedBuilding(intent.BuildingType)
	if !ok || r == nil {
		return errors.New("invalid_construction_site")
	}
	terrain := make(map[Point]Terrain, len(r.Terrain))
	for _, cell := range r.Terrain {
		terrain[Point{cell.X, cell.Y}] = cell
	}
	height := -1
	for y := intent.Tile.Y; y < intent.Tile.Y+building.Height; y++ {
		for x := intent.Tile.X; x < intent.Tile.X+building.Width; x++ {
			cell, exists := terrain[Point{x, y}]
			if !exists || !cell.ConstructionRights || !cell.Walkable || cell.Water != 0 ||
				cell.Slope != 0 || len(cell.GroundPaths) != 0 || len(cell.PathLayers) != 0 {
				return errors.New("construction_ground_unavailable")
			}
			if height >= 0 && cell.Height != height {
				return errors.New("construction_ground_uneven")
			}
			height = cell.Height
		}
	}
	site := constructionRect(intent)
	for _, entity := range r.Entities {
		if r.Destroyed[entity.ID] {
			continue
		}
		for _, rect := range entity.Geometry.Rects {
			if rectanglesOverlap(site, rect) {
				return errors.New("construction_park_obstructed")
			}
		}
		for _, cell := range entity.Geometry.Cells {
			if rectanglesOverlap(site, Rect{X: cell.X * 32, Y: cell.Y * 32, Width: 32, Height: 32}) {
				return errors.New("construction_park_obstructed")
			}
		}
	}
	return nil
}
