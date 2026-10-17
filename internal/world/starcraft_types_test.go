package world

import "testing"

func TestSupportedStarcraftTypes(t *testing.T) {
	if err := ValidateTypeDefinitions(unitDefinitions, buildingDefinitions); err != nil {
		t.Fatal(err)
	}
	if _, ok := SupportedUnit("Terran_Firebat"); ok {
		t.Fatal("unknown BWAPI type became supported")
	}
	if _, ok := SupportedBuilding("terran_supply_depot"); ok {
		t.Fatal("future building became supported")
	}
	marine, ok := SupportedUnit("terran_marine")
	if !ok || !marine.Controllable || marine.NativeType != "Terran_Marine" {
		t.Fatal(marine)
	}
	barracks, ok := SupportedBuilding("terran_barracks")
	if !ok || barracks.Width != 4 || barracks.Height != 3 || barracks.MaxHealth != 1000 || len(barracks.Production) != 1 || barracks.Production[0] != marine.ID {
		t.Fatal(barracks)
	}
	academy, ok := SupportedBuilding("terran_academy")
	if !ok || academy.NativeType != "Terran_Academy" || academy.Width != 3 || academy.Height != 2 ||
		academy.MaxHealth != 600 || len(academy.Production) != 0 {
		t.Fatal(academy)
	}
}

func TestInvalidStarcraftDefinitions(t *testing.T) {
	unit := unitDefinitions["terran_marine"]
	unit.ID = "wrong"
	if ValidateTypeDefinitions(map[string]UnitDefinition{"terran_marine": unit}, nil) == nil {
		t.Fatal("accepted mismatched ID")
	}
	building := buildingDefinitions["terran_barracks"]
	building.Production = []string{"terran_firebat"}
	if ValidateTypeDefinitions(unitDefinitions, map[string]BuildingDefinition{building.ID: building}) == nil {
		t.Fatal("accepted unsupported production")
	}
}
