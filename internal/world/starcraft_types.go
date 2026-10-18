package world

import "fmt"

// These are the StarCoaster integration types, not the complete BWAPI catalog.
// Native BWAPI type resolution lives in WorldStarcraftTypes.h.
type UnitDefinition struct {
	ID, NativeType, Race, Ownership, DisplayName, Visual, Movement string
	Controllable, Spawnable, VisibleIncomplete                   bool
	LegacyStaticBase                                             int
	Commands                                                     []string
}

type BuildingDefinition struct {
	ID, NativeType, ObjectID, DisplayName, Visual string
	Width, Height, MaxHealth                      int
	Production                                    []string
}

// BEGIN GENERATED STARCRAFT TYPES
var unitDefinitions = map[string]UnitDefinition{
	"terran_marine": {ID: "terran_marine", NativeType: "Terran_Marine", Race: "terran", Ownership: "player", DisplayName: "Marine", Visual: "terran_marine", Movement: "ground", Controllable: true, Spawnable: true, VisibleIncomplete: false, LegacyStaticBase: 1000, Commands: []string{"unit.move", "unit.attack", "unit.attack_move", "unit.hold", "unit.stop"}},
	"terran_firebat": {ID: "terran_firebat", NativeType: "Terran_Firebat", Race: "terran", Ownership: "player", DisplayName: "Firebat", Visual: "terran_firebat", Movement: "ground", Controllable: true, Spawnable: false, VisibleIncomplete: false, LegacyStaticBase: 0, Commands: []string{"unit.move", "unit.attack", "unit.attack_move", "unit.hold", "unit.stop"}},
	"terran_medic": {ID: "terran_medic", NativeType: "Terran_Medic", Race: "terran", Ownership: "player", DisplayName: "Medic", Visual: "terran_medic", Movement: "ground", Controllable: true, Spawnable: false, VisibleIncomplete: false, LegacyStaticBase: 0, Commands: []string{"unit.move", "unit.attack_move", "unit.hold", "unit.stop", "unit.heal"}},
	"terran_vulture": {ID: "terran_vulture", NativeType: "Terran_Vulture", Race: "terran", Ownership: "player", DisplayName: "Vulture", Visual: "terran_vulture", Movement: "ground", Controllable: true, Spawnable: false, VisibleIncomplete: false, LegacyStaticBase: 0, Commands: []string{"unit.move", "unit.attack", "unit.attack_move", "unit.hold", "unit.stop"}},
	"terran_goliath": {ID: "terran_goliath", NativeType: "Terran_Goliath", Race: "terran", Ownership: "player", DisplayName: "Goliath", Visual: "terran_goliath", Movement: "ground", Controllable: true, Spawnable: false, VisibleIncomplete: false, LegacyStaticBase: 0, Commands: []string{"unit.move", "unit.attack", "unit.attack_move", "unit.hold", "unit.stop"}},
	"zerg_zergling": {ID: "zerg_zergling", NativeType: "Zerg_Zergling", Race: "zerg", Ownership: "enemy", DisplayName: "Zergling", Visual: "zerg_zergling", Movement: "ground", Controllable: false, Spawnable: true, VisibleIncomplete: false, LegacyStaticBase: 2000, Commands: []string{}},
	"zerg_hydralisk": {ID: "zerg_hydralisk", NativeType: "Zerg_Hydralisk", Race: "zerg", Ownership: "enemy", DisplayName: "Hydralisk", Visual: "zerg_hydralisk", Movement: "ground", Controllable: false, Spawnable: true, VisibleIncomplete: false, LegacyStaticBase: 0, Commands: []string{}},
	"zerg_ultralisk": {ID: "zerg_ultralisk", NativeType: "Zerg_Ultralisk", Race: "zerg", Ownership: "enemy", DisplayName: "Ultralisk", Visual: "zerg_ultralisk", Movement: "ground", Controllable: false, Spawnable: true, VisibleIncomplete: false, LegacyStaticBase: 0, Commands: []string{}},
	"zerg_larva": {ID: "zerg_larva", NativeType: "Zerg_Larva", Race: "zerg", Ownership: "enemy", DisplayName: "Larva", Visual: "zerg_larva", Movement: "ground", Controllable: false, Spawnable: false, VisibleIncomplete: false, LegacyStaticBase: 0, Commands: []string{}},
	"zerg_egg": {ID: "zerg_egg", NativeType: "Zerg_Egg", Race: "zerg", Ownership: "enemy", DisplayName: "Egg", Visual: "zerg_egg", Movement: "ground", Controllable: false, Spawnable: false, VisibleIncomplete: true, LegacyStaticBase: 0, Commands: []string{}},
}

var buildingDefinitions = map[string]BuildingDefinition{
	"terran_barracks": {ID: "terran_barracks", NativeType: "Terran_Barracks", ObjectID: "starcoaster.scenery_large.terran_barracks", DisplayName: "Terran Barracks", Visual: "terran_barracks", Width: 4, Height: 3, MaxHealth: 1000, Production: []string{"terran_marine", "terran_firebat", "terran_medic"}},
	"terran_academy": {ID: "terran_academy", NativeType: "Terran_Academy", ObjectID: "starcoaster.scenery_large.terran_academy", DisplayName: "Terran Academy", Visual: "terran_academy", Width: 3, Height: 2, MaxHealth: 600, Production: []string{}},
	"terran_supply_depot": {ID: "terran_supply_depot", NativeType: "Terran_Supply_Depot", ObjectID: "starcoaster.scenery_large.terran_supply_depot", DisplayName: "Terran Supply Depot", Visual: "terran_supply_depot", Width: 3, Height: 2, MaxHealth: 500, Production: []string{}},
	"terran_factory": {ID: "terran_factory", NativeType: "Terran_Factory", ObjectID: "starcoaster.scenery_large.terran_factory", DisplayName: "Terran Factory", Visual: "terran_factory", Width: 4, Height: 3, MaxHealth: 1250, Production: []string{"terran_vulture", "terran_goliath"}},
	"terran_armory": {ID: "terran_armory", NativeType: "Terran_Armory", ObjectID: "starcoaster.scenery_large.terran_armory", DisplayName: "Terran Armory", Visual: "terran_armory", Width: 3, Height: 2, MaxHealth: 750, Production: []string{}},
	"zerg_hatchery": {ID: "zerg_hatchery", NativeType: "Zerg_Hatchery", ObjectID: "starcoaster.scenery_large.zerg_hatchery", DisplayName: "Zerg Hatchery", Visual: "zerg_hatchery", Width: 4, Height: 3, MaxHealth: 1250, Production: []string{"zerg_zergling"}},
	"zerg_spawning_pool": {ID: "zerg_spawning_pool", NativeType: "Zerg_Spawning_Pool", ObjectID: "starcoaster.scenery_large.zerg_spawning_pool", DisplayName: "Zerg Spawning Pool", Visual: "zerg_spawning_pool", Width: 3, Height: 2, MaxHealth: 750, Production: []string{}},
}

// END GENERATED STARCRAFT TYPES

func SupportedUnit(id string) (UnitDefinition, bool) {
	unit, ok := unitDefinitions[id]
	return unit, ok
}
func SupportedBuilding(id string) (BuildingDefinition, bool) {
	building, ok := buildingDefinitions[id]
	return building, ok
}

func ValidateTypeDefinitions(units map[string]UnitDefinition, buildings map[string]BuildingDefinition) error {
	objects := map[string]bool{}
	for key, unit := range units {
		if key == "" || key != unit.ID || unit.NativeType == "" || unit.Race == "" || unit.Ownership == "" || unit.DisplayName == "" || unit.Visual == "" {
			return fmt.Errorf("invalid unit definition %q", key)
		}
		if unit.Controllable && len(unit.Commands) == 0 {
			return fmt.Errorf("controllable unit %q has no commands", key)
		}
	}
	for key, building := range buildings {
		if key == "" || key != building.ID || building.NativeType == "" || building.ObjectID == "" || building.DisplayName == "" || building.Width < 1 || building.Height < 1 || building.MaxHealth < 1 || objects[building.ObjectID] {
			return fmt.Errorf("invalid building definition %q", key)
		}
		objects[building.ObjectID] = true
		for _, unit := range building.Production {
			if _, ok := units[unit]; !ok {
				return fmt.Errorf("building %q produces unsupported unit %q", key, unit)
			}
		}
	}
	return nil
}
