#pragma once

#include <BWAPI.h>
#include <string>
#include <vector>

// Only types integrated with StarCoaster belong here. BWAPI retains all
// gameplay rules and resolves native types in this module.
struct WorldUnitType {
    const char* id;
    BWAPI::UnitType native;
    const char* race;
    const char* ownership;
    bool controllable;
    bool spawnable;
    bool visibleIncomplete;
    const char* visual;
    int legacyStaticBase;
    int deathDisplayFrames;
};

struct WorldBuildingType {
    const char* id;
    BWAPI::UnitType native;
    const char* objectID;
    int width;
    int height;
    const char* name;
    bool production;
    std::vector<std::string> trainable;
};

inline const std::vector<WorldUnitType>& worldUnitTypes() {
    static const std::vector<WorldUnitType> types = {
        // BEGIN GENERATED STARCRAFT UNITS
        {"terran_marine", BWAPI::UnitTypes::Terran_Marine, "terran", "player", true, true, false, "terran_marine", 1000, 16},
        {"terran_firebat", BWAPI::UnitTypes::Terran_Firebat, "terran", "player", true, false, false, "terran_firebat", 0, 16},
        {"terran_medic", BWAPI::UnitTypes::Terran_Medic, "terran", "player", true, false, false, "terran_medic", 0, 16},
        {"terran_vulture", BWAPI::UnitTypes::Terran_Vulture, "terran", "player", true, false, false, "terran_vulture", 0, 16},
        {"terran_goliath", BWAPI::UnitTypes::Terran_Goliath, "terran", "player", true, false, false, "terran_goliath", 0, 16},
        {"zerg_zergling", BWAPI::UnitTypes::Zerg_Zergling, "zerg", "enemy", false, true, false, "zerg_zergling", 2000, 14},
        {"zerg_hydralisk", BWAPI::UnitTypes::Zerg_Hydralisk, "zerg", "enemy", false, true, false, "zerg_hydralisk", 0, 16},
        {"zerg_ultralisk", BWAPI::UnitTypes::Zerg_Ultralisk, "zerg", "enemy", false, true, false, "zerg_ultralisk", 0, 20},
        {"zerg_larva", BWAPI::UnitTypes::Zerg_Larva, "zerg", "enemy", false, false, false, "zerg_larva", 0, 87},
        {"zerg_egg", BWAPI::UnitTypes::Zerg_Egg, "zerg", "enemy", false, false, true, "zerg_egg", 0, 93},

        // END GENERATED STARCRAFT UNITS
    };
    return types;
}

inline const WorldUnitType* worldUnitType(const std::string& id) {
    for (const auto& type : worldUnitTypes()) if (id == type.id) return &type;
    return nullptr;
}

inline const WorldUnitType* worldUnitType(BWAPI::UnitType native) {
    for (const auto& type : worldUnitTypes()) if (type.native == native) return &type;
    return nullptr;
}

inline const std::vector<WorldBuildingType>& worldBuildingTypes() {
    static const std::vector<WorldBuildingType> types = {
        // BEGIN GENERATED STARCRAFT BUILDINGS
        {"terran_barracks", BWAPI::UnitTypes::Terran_Barracks, "starcoaster.scenery_large.terran_barracks", 4, 3, "Terran Barracks", true, {"terran_marine", "terran_firebat", "terran_medic"}},
        {"terran_academy", BWAPI::UnitTypes::Terran_Academy, "starcoaster.scenery_large.terran_academy", 3, 2, "Terran Academy", false, {}},
        {"terran_supply_depot", BWAPI::UnitTypes::Terran_Supply_Depot, "starcoaster.scenery_large.terran_supply_depot", 3, 2, "Terran Supply Depot", false, {}},
        {"terran_factory", BWAPI::UnitTypes::Terran_Factory, "starcoaster.scenery_large.terran_factory", 4, 3, "Terran Factory", true, {"terran_vulture", "terran_goliath"}},
        {"terran_armory", BWAPI::UnitTypes::Terran_Armory, "starcoaster.scenery_large.terran_armory", 3, 2, "Terran Armory", false, {}},
        {"zerg_hatchery", BWAPI::UnitTypes::Zerg_Hatchery, "starcoaster.scenery_large.zerg_hatchery", 4, 3, "Zerg Hatchery", true, {"zerg_zergling"}},
        {"zerg_spawning_pool", BWAPI::UnitTypes::Zerg_Spawning_Pool, "starcoaster.scenery_large.zerg_spawning_pool", 3, 2, "Zerg Spawning Pool", false, {}},

        // END GENERATED STARCRAFT BUILDINGS
    };
    return types;
}

inline const WorldBuildingType* worldBuildingType(const std::string& id) {
    for (const auto& type : worldBuildingTypes()) if (id == type.id) return &type;
    return nullptr;
}

inline const WorldBuildingType* worldBuildingType(BWAPI::UnitType native) {
    for (const auto& type : worldBuildingTypes()) if (type.native == native) return &type;
    return nullptr;
}

inline bool worldCanProduce(const WorldBuildingType& building, const std::string& unitID) {
    for (const auto& id : building.trainable) if (unitID == id) return true;
    return false;
}
