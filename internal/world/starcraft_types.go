package world

import "fmt"

// These are the StarCoaster integration types, not the complete BWAPI catalog.
// Native BWAPI type resolution lives in WorldStarcraftTypes.h.
type UnitDefinition struct {
	ID, NativeType, Race, Ownership, DisplayName, Visual string
	Controllable                                         bool
	Commands                                             []string
}

type BuildingDefinition struct {
	ID, NativeType, ObjectID, DisplayName, Visual string
	Width, Height, MaxHealth                      int
	Production                                    []string
}

// BEGIN GENERATED STARCRAFT TYPES
var unitDefinitions = map[string]UnitDefinition{
	"terran_marine": {ID: "terran_marine", NativeType: "Terran_Marine", Race: "terran", Ownership: "player", DisplayName: "Marine", Visual: "terran_marine", Controllable: true, Commands: []string{"unit.move", "unit.attack", "unit.attack_move", "unit.hold", "unit.stop"}},
	"terran_firebat": {ID: "terran_firebat", NativeType: "Terran_Firebat", Race: "terran", Ownership: "player", DisplayName: "Firebat", Visual: "terran_firebat", Controllable: true, Commands: []string{"unit.move", "unit.attack", "unit.attack_move", "unit.hold", "unit.stop"}},
	"zerg_zergling": {ID: "zerg_zergling", NativeType: "Zerg_Zergling", Race: "zerg", Ownership: "enemy", DisplayName: "Zergling", Visual: "zerg_zergling", Controllable: false, Commands: []string{}},
}

var buildingDefinitions = map[string]BuildingDefinition{
	"terran_barracks": {ID: "terran_barracks", NativeType: "Terran_Barracks", ObjectID: "starcoaster.scenery_large.terran_barracks", DisplayName: "Terran Barracks", Visual: "terran_barracks", Width: 4, Height: 3, MaxHealth: 1000, Production: []string{"terran_marine", "terran_firebat"}},
	"terran_academy": {ID: "terran_academy", NativeType: "Terran_Academy", ObjectID: "starcoaster.scenery_large.terran_academy", DisplayName: "Terran Academy", Visual: "terran_academy", Width: 3, Height: 2, MaxHealth: 600, Production: []string{}},
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
