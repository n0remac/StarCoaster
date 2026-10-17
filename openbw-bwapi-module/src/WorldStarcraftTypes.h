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
    bool controllable;
    const char* visual;
    int legacyStaticBase;
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
        {"terran_marine", BWAPI::UnitTypes::Terran_Marine, "terran", true, "terran_marine", 1000},
        {"terran_firebat", BWAPI::UnitTypes::Terran_Firebat, "terran", true, "terran_firebat", 0},
        {"terran_medic", BWAPI::UnitTypes::Terran_Medic, "terran", true, "terran_medic", 0},
        {"terran_vulture", BWAPI::UnitTypes::Terran_Vulture, "terran", true, "terran_vulture", 0},
        {"zerg_zergling", BWAPI::UnitTypes::Zerg_Zergling, "zerg", false, "zerg_zergling", 2000},
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
        {"terran_barracks", BWAPI::UnitTypes::Terran_Barracks,
            "starcoaster.scenery_large.terran_barracks", 4, 3, "Terran Barracks", true,
            {"terran_marine", "terran_firebat", "terran_medic"}},
        {"terran_academy", BWAPI::UnitTypes::Terran_Academy,
            "starcoaster.scenery_large.terran_academy", 3, 2, "Terran Academy", false,
            {}},
        {"terran_supply_depot", BWAPI::UnitTypes::Terran_Supply_Depot,
            "starcoaster.scenery_large.terran_supply_depot", 3, 2, "Terran Supply Depot", false,
            {}},
        {"terran_factory", BWAPI::UnitTypes::Terran_Factory,
            "starcoaster.scenery_large.terran_factory", 4, 3, "Terran Factory", true,
            {"terran_vulture"}},
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
