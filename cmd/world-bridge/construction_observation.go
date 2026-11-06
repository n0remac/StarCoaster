package main

import (
	"errors"
	"log"

	"starcoaster/internal/world"
)

type nativeConstructionObservation struct {
	IntentID        string `json:"intent_id"`
	Type            string `json:"type"`
	Owner           int    `json:"owner"`
	TileX           int    `json:"tile_x"`
	TileY           int    `json:"tile_y"`
	State           string `json:"state"`
	NativeID        string `json:"native_id"`
	RemainingFrames int    `json:"remaining_frames"`
	Health          int    `json:"health"`
	Frame           int    `json:"-"`
}

func (s *service) watchConstruction(intent world.ConstructionIntent) error {
	if s.bw == nil || s.controller == nil {
		return errors.New("native_participant_unavailable")
	}
	payload := map[string]any{"intent_id": intent.ID, "building_type": intent.BuildingType,
		"tile_x": s.transform.TileX(intent.Tile.X), "tile_y": s.transform.TileY(intent.Tile.Y)}
	if err := s.emit(s.bw, "construction.watch", s.registry.Session, s.registry.Revision, payload); err != nil {
		return err
	}
	return s.emit(s.controller, "construction.watch", s.registry.Session, s.registry.Revision, payload)
}

func (s *service) restoreConstructionWatches() {
	if s.construction == nil {
		return
	}
	for _, intent := range s.construction.Intents {
		_ = s.emit(s.park, "construction.state", s.registry.Session, s.registry.Revision,
			map[string]any{"intent_id": intent.ID, "state": intent.State,
				"building_type": intent.BuildingType, "tile_x": intent.Tile.X, "tile_y": intent.Tile.Y,
				"native_id": intent.NativeID, "projection_id": intent.ProjectionID})
		if intent.State == "rejected" || intent.State == "canceled" || intent.State == "destroyed" {
			continue
		}
		if err := s.watchConstruction(intent); err != nil {
			log.Printf("construction watch unavailable intent=%s: %v", intent.ID, err)
		}
	}
}

func (s *service) recordConstructionObservation(p *peer, m world.Envelope, role string) {
	if s.construction == nil || m.Session != s.registry.Session || m.Revision != s.registry.Revision ||
		(role == "publisher" && p != s.bw) || (role == "controller" && p != s.controller) {
		s.ack(p, m, false, "invalid_construction_source")
		return
	}
	var observation nativeConstructionObservation
	if m.Decode(&observation) != nil {
		s.ack(p, m, false, "invalid_construction_observation")
		return
	}
	intent, exists := s.construction.Intents[observation.IntentID]
	if !exists || observation.Type != intent.BuildingType || observation.Owner != 1 ||
		observation.TileX != s.transform.TileX(intent.Tile.X) ||
		observation.TileY != s.transform.TileY(intent.Tile.Y) ||
		observation.RemainingFrames < 0 || observation.Health < 0 ||
		(observation.State != "absent" && observation.State != "incomplete" && observation.State != "paused" && observation.State != "completed" && observation.State != "ambiguous") {
		s.ack(p, m, false, "construction_identity_mismatch")
		return
	}
	if observation.State == "ambiguous" {
		_ = s.emit(s.park, "construction.state", m.Session, m.Revision,
			map[string]any{"intent_id": intent.ID, "state": "projection_failed", "reason": "ambiguous_native_site"})
		return
	}
	if observation.State != "absent" && !unitIDPatternNative(observation.NativeID) {
		s.ack(p, m, false, "invalid_native_building_id")
		return
	}
	if s.constructionSeen == nil {
		s.constructionSeen = map[string]map[string]nativeConstructionObservation{}
	}
	if s.constructionSeen[intent.ID] == nil {
		s.constructionSeen[intent.ID] = map[string]nativeConstructionObservation{}
	}
	observation.Frame = m.BWTick
	s.constructionSeen[intent.ID][role] = observation
	publisher, pOK := s.constructionSeen[intent.ID]["publisher"]
	controller, cOK := s.constructionSeen[intent.ID]["controller"]
	if !pOK || !cOK {
		return
	}
	if publisher.State == "absent" && controller.State == "absent" {
		if intent.NativeID != "" && intent.State != "canceled" && intent.State != "destroyed" {
			terminal := "destroyed"
			if intent.CancelRequested {
				terminal = "canceled"
			}
			if err := s.construction.Terminal(intent.ID, terminal); err != nil {
				log.Printf("construction terminal: %v", err)
				return
			}
			_ = s.emit(s.park, "construction.state", m.Session, m.Revision,
				map[string]any{"intent_id": intent.ID, "state": terminal,
					"publisher_frame": publisher.Frame, "controller_frame": controller.Frame})
		}
		return
	}
	if publisher.State == "absent" || controller.State == "absent" ||
		publisher.NativeID == "" || controller.NativeID == "" {
		return
	}
	if intent.NativeID == "" {
		generation := uint64(1)
		if intent.GeyserSiteID != "" {
			generation = intent.GeyserGeneration + 1
		}
		if err := s.construction.Bind(world.ConstructionObservation{IntentID: intent.ID,
			NativeID: publisher.NativeID, ControllerNativeID: controller.NativeID,
			Type: intent.BuildingType, Owner: 1, Tile: intent.Tile, Generation: generation}); err != nil {
			log.Printf("construction native binding failed intent=%s: %v", intent.ID, err)
			return
		}
		intent = s.construction.Intents[intent.ID]
		log.Printf("construction bound intent=%s type=%s native_publisher=%s native_controller=%s tile=%d,%d frame=%d/%d",
			intent.ID, intent.BuildingType, publisher.NativeID, controller.NativeID,
			intent.Tile.X, intent.Tile.Y, publisher.Frame, controller.Frame)
	}
	if intent.NativeID != publisher.NativeID || intent.ControllerNativeID != controller.NativeID {
		return
	}
	state := "constructing"
	if publisher.State == "paused" && controller.State == "paused" {
		state = "paused"
		log.Printf("construction paused intent=%s native=%s remaining=%d frame=%d/%d",
			intent.ID, intent.NativeID, publisher.RemainingFrames, publisher.Frame, controller.Frame)
	}
	if publisher.State == "completed" && controller.State == "completed" {
		if err := s.construction.Complete(intent.ID, intent.NativeID); err != nil {
			log.Printf("construction completion: %v", err)
		}
		state = "completed"
		log.Printf("construction completed intent=%s native=%s frame=%d/%d",
			intent.ID, intent.NativeID, publisher.Frame, controller.Frame)
	}
	_ = s.emit(s.park, "construction.state", m.Session, m.Revision,
		map[string]any{"intent_id": intent.ID, "state": state, "building_type": intent.BuildingType,
			"tile_x": intent.Tile.X, "tile_y": intent.Tile.Y,
			"native_id": publisher.NativeID, "controller_native_id": controller.NativeID,
			"remaining_frames": publisher.RemainingFrames, "health": publisher.Health,
			"publisher_frame": publisher.Frame, "controller_frame": controller.Frame,
			"projection_id": intent.ProjectionID})
}

func unitIDPatternNative(id string) bool {
	if id == "" {
		return false
	}
	for _, c := range id {
		if c < '0' || c > '9' {
			return false
		}
	}
	return true
}
