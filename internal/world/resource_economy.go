package world

import (
	"regexp"
)

var observedNativeID = regexp.MustCompile(`^[0-9]+$`)

// ResourceObservation is an OpenBW fact about an authored logical site. The
// CHK record number is never a binding; each participant reports its BWAPI ID.
type ResourceObservation struct {
	SiteID     string `json:"site_id"`
	Generation uint64 `json:"generation"`
	NativeID   string `json:"native_id"`
	Type       string `json:"type"`
	Owner      int    `json:"owner"`
	X          int    `json:"x"`
	Y          int    `json:"y"`
	Amount     int    `json:"amount"`
	Lifecycle  string `json:"lifecycle"`
}

type ResourceState struct {
	ResourceObservation
	PublisherNativeID  string `json:"publisher_native_id"`
	ControllerNativeID string `json:"controller_native_id"`
}

type resourceSite struct {
	typeID   string
	x, y     int
	observed map[string]ResourceObservation
	last     ResourceState
}

type ResourceLedger struct {
	session string
	sites   map[string]*resourceSite
}

func (l *ResourceLedger) Latest(siteID string) (ResourceState, bool) {
	if l == nil || l.sites[siteID] == nil || l.sites[siteID].last.Generation == 0 {
		return ResourceState{}, false
	}
	return l.sites[siteID].last, true
}

func NewResourceLedger(s *Scenario, session string) *ResourceLedger {
	l := &ResourceLedger{session: session, sites: map[string]*resourceSite{}}
	if s == nil || s.Economy == nil || s.Economy.Mode != "finite" {
		return l
	}
	for _, entity := range s.Economy.StartingEntities {
		resource, ok := SupportedResource(entity.Type)
		if !ok {
			continue
		}
		x := (entity.Tile[0]+(256-s.ParkSize[0])/2)*32 + resource.Width*16
		y := (entity.Tile[1]+(256-s.ParkSize[1])/2)*32 + resource.Height*16
		l.sites[entity.ID] = &resourceSite{typeID: entity.Type, x: x, y: y,
			observed: map[string]ResourceObservation{}}
	}
	return l
}

// Observe publishes only when both native participants agree on the type,
// generation, amount and lifecycle. Their native IDs may legitimately differ.
func (l *ResourceLedger) Observe(role string, observation ResourceObservation) (ResourceState, bool) {
	var zero ResourceState
	site := l.sites[observation.SiteID]
	if site == nil || (role != "publisher" && role != "controller") ||
		observation.Generation == 0 || observation.X != site.x || observation.Y != site.y ||
		observation.Amount < 0 || observation.Amount > 65535 {
		return zero, false
	}
	switch observation.Lifecycle {
	case "deposit":
		if observation.Type != site.typeID || observation.Owner != 11 ||
			!observedNativeID.MatchString(observation.NativeID) {
			return zero, false
		}
	case "refinery":
		if site.typeID != "vespene_geyser" || observation.Type != "terran_refinery" ||
			observation.Owner != 1 || !observedNativeID.MatchString(observation.NativeID) {
			return zero, false
		}
	case "absent":
		if observation.Type != "" || observation.NativeID != "" || observation.Amount != 0 {
			return zero, false
		}
	default:
		return zero, false
	}
	old := site.observed[role]
	if observation.Generation < old.Generation ||
		(observation.Generation == old.Generation && observation.NativeID != old.NativeID) {
		return zero, false
	}
	site.observed[role] = observation
	publisher, pOK := site.observed["publisher"]
	controller, cOK := site.observed["controller"]
	if !pOK || !cOK || publisher.Generation != controller.Generation ||
		publisher.Type != controller.Type || publisher.Owner != controller.Owner ||
		publisher.Amount != controller.Amount || publisher.Lifecycle != controller.Lifecycle {
		return zero, false
	}
	state := ResourceState{ResourceObservation: publisher,
		PublisherNativeID: publisher.NativeID, ControllerNativeID: controller.NativeID}
	if state == site.last {
		return zero, false
	}
	site.last = state
	return state, true
}
