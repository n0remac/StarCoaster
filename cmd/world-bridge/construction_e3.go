package main

import (
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"log"

	"starcoaster/internal/world"
)

func (s *service) finiteEconomy() bool {
	return s.scenario != nil && s.scenario.Economy != nil && s.scenario.Economy.Mode == "finite"
}

func (s *service) initConstruction(session string) error {
	if !s.finiteEconomy() {
		s.construction = nil
		return nil
	}
	if s.construction != nil && s.construction.Session == session {
		return nil
	}
	if s.spawnJournalPath == "" {
		return errors.New("finite_economy_requires_construction_journal")
	}
	digest := sha256.Sum256([]byte(session))
	path := s.spawnJournalPath + ".construction-" + hex.EncodeToString(digest[:8]) + ".json"
	ledger, err := world.LoadConstructionLedger(path, session)
	if err != nil {
		return err
	}
	s.construction = ledger
	log.Printf("construction journal session=%s intents=%d", session, len(ledger.Intents))
	return nil
}

func (s *service) validateFinitePatch(patch world.Patch) error {
	if !s.finiteEconomy() {
		return nil
	}
	if s.construction == nil {
		return errors.New("construction_journal_unavailable")
	}
	if err := s.construction.ValidateFinitePatch(patch); err != nil {
		return err
	}
	for _, authored := range s.scenario.InitialStructures {
		building, ok := world.SupportedBuilding(authored.Type)
		if !ok || len(authored.Type) < 7 || authored.Type[:7] != "terran_" {
			continue
		}
		baseID := "scenario:" + authored.ID
		site := world.Rect{X: authored.Tile[0] * 32, Y: authored.Tile[1] * 32,
			Width: building.Width * 32, Height: building.Height * 32}
		for _, id := range patch.Removals {
			if id == baseID {
				return errors.New("native_base_removal_requires_native_destruction")
			}
			if s.registry != nil {
				if entity, exists := s.registry.Entities[id]; exists && constructionEntityOverlaps(entity, site) {
					return errors.New("native_base_site_reserved")
				}
			}
		}
		for _, entity := range append(append([]world.Entity{}, patch.Additions...), patch.Modifications...) {
			if entity.ID == baseID || constructionEntityOverlaps(entity, site) {
				return errors.New("native_base_site_reserved")
			}
		}
		for _, cell := range patch.Terrain {
			if cell.X >= authored.Tile[0] && cell.X < authored.Tile[0]+building.Width &&
				cell.Y >= authored.Tile[1] && cell.Y < authored.Tile[1]+building.Height {
				return errors.New("native_base_site_reserved")
			}
		}
	}
	return nil
}

func constructionEntityOverlaps(entity world.Entity, site world.Rect) bool {
	for _, rect := range entity.Geometry.Rects {
		if rect.X < site.X+site.Width && site.X < rect.X+rect.Width &&
			rect.Y < site.Y+site.Height && site.Y < rect.Y+rect.Height {
			return true
		}
	}
	for _, cell := range entity.Geometry.Cells {
		if cell.X*32 < site.X+site.Width && site.X < (cell.X+1)*32 &&
			cell.Y*32 < site.Y+site.Height && site.Y < (cell.Y+1)*32 {
			return true
		}
	}
	return false
}

func (s *service) rejectDirectEconomySpawn() bool { return s.finiteEconomy() }

// Authored starting SCVs predate the runtime actor journal. Their canonical
// IDs are published by native snapshots, and the Terran BWAPI controller
// checks the exact live unit, owner and type before issuing any order.
func (s *service) constructionWorker(id string) bool {
	if !unitIDPattern.MatchString(id) || s.actors == nil {
		return false
	}
	if worker, known := s.actors.Lookup(id); known {
		return worker.Identity.Type == "terran_scv" && worker.Identity.Owner == 1 &&
			s.actors.Commandable(id)
	}
	return true
}

func (s *service) validateFiniteSnapshot(entities []world.Entity) error {
	if !s.finiteEconomy() {
		return nil
	}
	if s.construction == nil {
		return errors.New("construction_journal_unavailable")
	}
	for _, entity := range entities {
		if entity.Kind != "structure" || len(entity.Type) < 7 || entity.Type[:7] != "terran_" {
			continue
		}
		authored := false
		for _, structure := range s.scenario.InitialStructures {
			if entity.ID == "scenario:"+structure.ID && entity.Type == structure.Type &&
				entity.Position.X == structure.Tile[0]*32 && entity.Position.Y == structure.Tile[1]*32 {
				building, ok := world.SupportedBuilding(structure.Type)
				if !ok || entity.Owner != 1 || !finiteAuthoredFootprint(entity, structure.Tile, building) {
					return errors.New("native_base_snapshot_mismatch")
				}
				authored = true
				break
			}
		}
		if authored {
			if s.construction.DestroyedAuthored[entity.ID] {
				return errors.New("destroyed_native_base_reintroduced")
			}
			continue
		}
		if err := s.construction.ValidateFinitePatch(world.Patch{Additions: []world.Entity{entity}}); err != nil {
			return err
		}
	}
	return nil
}

func finiteAuthoredFootprint(entity world.Entity, tile [2]int, building world.BuildingDefinition) bool {
	if len(entity.Geometry.Rects) == 0 {
		return false
	}
	left, top := tile[0]*32, tile[1]*32
	right, bottom := left+building.Width*32, top+building.Height*32
	for _, rect := range entity.Geometry.Rects {
		if rect.Width <= 0 || rect.Height <= 0 || rect.X < left || rect.Y < top ||
			rect.X+rect.Width > right || rect.Y+rect.Height > bottom {
			return false
		}
	}
	for y := top; y < bottom; y += 32 {
		for x := left; x < right; x += 32 {
			covered := false
			for _, rect := range entity.Geometry.Rects {
				if rect.X <= x && rect.Y <= y && rect.X+rect.Width >= x+32 && rect.Y+rect.Height >= y+32 {
					covered = true
					break
				}
			}
			if !covered {
				return false
			}
		}
	}
	return true
}

func (s *service) markFiniteAuthoredDestroyed(id string) error {
	if !s.finiteEconomy() || s.construction == nil {
		return nil
	}
	for _, authored := range s.scenario.InitialStructures {
		if id == "scenario:"+authored.ID {
			return s.construction.MarkAuthoredDestroyed(id)
		}
	}
	return nil
}

func (s *service) prepareNativeBuild(command *worldCommand) (bool, error) {
	if !s.finiteEconomy() || s.construction == nil || len(command.UnitIDs) != 1 || s.actors == nil {
		return false, errors.New("native_construction_unavailable")
	}
	if !s.constructionWorker(command.UnitIDs[0]) {
		return false, errors.New("construction_worker_unavailable")
	}
	building, supported := world.SupportedBuilding(command.BuildingType)
	if !supported || len(command.BuildingType) < 7 || command.BuildingType[:7] != "terran_" {
		return false, errors.New("unsupported_construction_type")
	}
	intent := world.ConstructionIntent{ID: fmt.Sprintf("build:%d:%d", command.PlayerID, command.RequestID),
		WorkerID: command.UnitIDs[0], BuildingType: command.BuildingType,
		Tile: world.Point{X: command.TileX, Y: command.TileY}}
	if prior, exists := s.construction.Intents[intent.ID]; exists {
		if prior.WorkerID != intent.WorkerID || prior.BuildingType != intent.BuildingType || prior.Tile != intent.Tile ||
			(command.BuildingType == "terran_refinery" && prior.GeyserSiteID != command.TargetID) {
			return false, errors.New("conflicting_construction_request")
		}
		_ = s.emit(s.park, "construction.state", s.registry.Session, s.registry.Revision,
			map[string]any{"intent_id": prior.ID, "state": prior.PublishedState(), "building_type": prior.BuildingType,
				"tile_x": prior.Tile.X, "tile_y": prior.Tile.Y,
				"native_id": prior.NativeID, "projection_id": prior.ProjectionID})
		return false, nil
	}
	if command.BuildingType == "terran_refinery" {
		state, ok := s.resources.Latest(command.TargetID)
		if !ok || state.Type != "vespene_geyser" || state.Lifecycle != "deposit" ||
			state.Owner != 11 || state.PublisherNativeID == "" || state.ControllerNativeID == "" ||
			(state.X-building.Width*16)/32 != s.transform.TileX(command.TileX) ||
			(state.Y-building.Height*16)/32 != s.transform.TileY(command.TileY) {
			return false, errors.New("invalid_geyser_target")
		}
		intent.GeyserSiteID, intent.GeyserGeneration, intent.GeyserNativeID, intent.GeyserControllerID =
			state.SiteID, state.Generation, state.PublisherNativeID, state.ControllerNativeID
		command.TargetNativeID = state.ControllerNativeID
		command.NativeGeneration = state.Generation
	} else if command.TargetID != "" {
		return false, errors.New("unexpected_construction_target")
	}
	if err := world.ValidateConstructionSite(s.registry, intent); err != nil {
		return false, err
	}
	if err := s.construction.Reserve(intent, s.registry.Width, s.registry.Height); err != nil {
		return false, err
	}
	command.IntentID = intent.ID
	command.NativeTileX, command.NativeTileY = s.transform.TileX(intent.Tile.X), s.transform.TileY(intent.Tile.Y)
	if !s.construction.MayDispatch(intent.ID) {
		prior := s.construction.Intents[intent.ID]
		_ = s.emit(s.park, "construction.state", s.registry.Session, s.registry.Revision,
			map[string]any{"intent_id": intent.ID, "state": prior.PublishedState(),
				"building_type": prior.BuildingType, "tile_x": prior.Tile.X, "tile_y": prior.Tile.Y,
				"native_id": prior.NativeID, "projection_id": prior.ProjectionID})
		return false, nil
	}
	if err := s.watchConstruction(intent); err != nil {
		return false, err
	}
	if err := s.construction.MarkDispatched(intent.ID); err != nil {
		return false, err
	}
	_ = s.emit(s.park, "construction.state", s.registry.Session, s.registry.Revision,
		map[string]any{"intent_id": intent.ID, "state": "requested", "building_type": intent.BuildingType,
			"tile_x": intent.Tile.X, "tile_y": intent.Tile.Y})
	return true, nil
}

func (s *service) prepareNativeConstructionControl(command *worldCommand) (bool, error) {
	if !s.finiteEconomy() || s.construction == nil {
		return false, errors.New("native_construction_unavailable")
	}
	intent, exists := s.construction.Intents[command.TargetID]
	if !exists || intent.NativeID == "" || intent.ControllerNativeID == "" ||
		intent.State == "destroyed" || intent.State == "canceled" || intent.State == "rejected" ||
		intent.State == "completed" {
		return false, errors.New("construction_target_unavailable")
	}
	if command.Verb == "unit.resume_construction" {
		if len(command.UnitIDs) != 1 || s.actors == nil {
			return false, errors.New("construction_worker_unavailable")
		}
		if !s.constructionWorker(command.UnitIDs[0]) {
			return false, errors.New("construction_worker_unavailable")
		}
	} else {
		if len(command.UnitIDs) != 0 {
			return false, errors.New("invalid_construction_cancel")
		}
		if intent.CancelRequested {
			return false, nil
		}
		if err := s.construction.MarkCancelRequested(intent.ID); err != nil {
			return false, err
		}
	}
	command.IntentID, command.BuildingType = intent.ID, intent.BuildingType
	command.NativeTileX, command.NativeTileY = s.transform.TileX(intent.Tile.X), s.transform.TileY(intent.Tile.Y)
	command.TargetNativeID, command.NativeGeneration = intent.ControllerNativeID, intent.NativeGeneration
	return true, nil
}
