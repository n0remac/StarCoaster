package world

import "testing"

func TestSupportedStarcraftTypes(t *testing.T) {
	if err := ValidateTypeDefinitions(unitDefinitions, buildingDefinitions); err != nil {
		t.Fatal(err)
	}
	if _, ok := SupportedUnit("Terran_Firebat"); ok {
		t.Fatal("unknown BWAPI type became supported")
	}
	if _, ok := SupportedBuilding("terran_starport"); ok {
		t.Fatal("unsupported building became supported")
	}
	marine, ok := SupportedUnit("terran_marine")
	if !ok || !marine.Controllable || marine.NativeType != "Terran_Marine" {
		t.Fatal(marine)
	}
	firebat, ok := SupportedUnit("terran_firebat")
	if !ok || !firebat.Controllable || firebat.NativeType != "Terran_Firebat" ||
		firebat.Ownership != "player" || len(firebat.Commands) != len(marine.Commands) {
		t.Fatal(firebat)
	}
	medic, ok := SupportedUnit("terran_medic")
	if !ok || !medic.Controllable || medic.NativeType != "Terran_Medic" || medic.Ownership != "player" {
		t.Fatal(medic)
	}
	vulture, ok := SupportedUnit("terran_vulture")
	if !ok || !vulture.Controllable || vulture.NativeType != "Terran_Vulture" || vulture.Ownership != "player" {
		t.Fatal(vulture)
	}
	goliath, ok := SupportedUnit("terran_goliath")
	if !ok || !goliath.Controllable || goliath.NativeType != "Terran_Goliath" || goliath.Ownership != "player" ||
		len(goliath.Commands) != len(vulture.Commands) {
		t.Fatal(goliath)
	}
	barracks, ok := SupportedBuilding("terran_barracks")
	if !ok || barracks.Width != 4 || barracks.Height != 3 || barracks.MaxHealth != 1000 ||
		len(barracks.Production) != 3 || barracks.Production[0] != marine.ID ||
		barracks.Production[1] != firebat.ID || barracks.Production[2] != medic.ID {
		t.Fatal(barracks)
	}
	academy, ok := SupportedBuilding("terran_academy")
	if !ok || academy.NativeType != "Terran_Academy" || academy.Width != 3 || academy.Height != 2 ||
		academy.MaxHealth != 600 || len(academy.Production) != 0 {
		t.Fatal(academy)
	}
	depot, ok := SupportedBuilding("terran_supply_depot")
	if !ok || depot.NativeType != "Terran_Supply_Depot" || depot.Width != 3 || depot.Height != 2 ||
		depot.MaxHealth != 500 || len(depot.Production) != 0 {
		t.Fatal(depot)
	}
	factory, ok := SupportedBuilding("terran_factory")
	if !ok || factory.NativeType != "Terran_Factory" || factory.Width != 4 || factory.Height != 3 ||
		factory.MaxHealth != 1250 || len(factory.Production) != 2 || factory.Production[0] != vulture.ID ||
		factory.Production[1] != goliath.ID {
		t.Fatal(factory)
	}
	armory, ok := SupportedBuilding("terran_armory")
	if !ok || armory.NativeType != "Terran_Armory" || armory.Width != 3 || armory.Height != 2 ||
		armory.MaxHealth != 750 || len(armory.Production) != 0 {
		t.Fatal(armory)
	}
}

func TestInvalidStarcraftDefinitions(t *testing.T) {
	unit := unitDefinitions["terran_marine"]
	unit.ID = "wrong"
	if ValidateTypeDefinitions(map[string]UnitDefinition{"terran_marine": unit}, nil) == nil {
		t.Fatal("accepted mismatched ID")
	}
	building := buildingDefinitions["terran_barracks"]
	building.Production = []string{"terran_ghost"}
	if ValidateTypeDefinitions(unitDefinitions, map[string]BuildingDefinition{building.ID: building}) == nil {
		t.Fatal("accepted unsupported production")
	}
}
