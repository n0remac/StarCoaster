#pragma once

#include <BWAPI.h>
#include <initializer_list>
#include <string>

// Only types integrated with StarCoaster belong here. BWAPI retains all
// gameplay rules and resolves native types in this module.
struct WorldUnitType {
    const char* id;
    BWAPI::UnitType native;
    const char* race;
    bool controllable;
    const char* visual;
};

struct WorldBuildingType {
    const char* id;
    BWAPI::UnitType native;
    const char* objectID;
    int width;
    int height;
    const char* name;
    bool production;
    std::initializer_list<const char*> trainable;
};

inline const WorldUnitType* worldUnitType(const std::string& id) {
    static const WorldUnitType types[] = {
        {"terran_marine", BWAPI::UnitTypes::Terran_Marine, "terran", true, "terran_marine"},
        {"zerg_zergling", BWAPI::UnitTypes::Zerg_Zergling, "zerg", false, "zerg_zergling"},
    };
    for (const auto& type : types) if (id == type.id) return &type;
    return nullptr;
}

inline const WorldUnitType* worldUnitType(BWAPI::UnitType native) {
    for (const auto* id : {"terran_marine", "zerg_zergling"}) {
        const auto* type = worldUnitType(id);
        if (type->native == native) return type;
    }
    return nullptr;
}

inline const WorldBuildingType* worldBuildingType(const std::string& id) {
    static const WorldBuildingType types[] = {
        {"terran_barracks", BWAPI::UnitTypes::Terran_Barracks,
            "starcoaster.scenery_large.terran_barracks", 4, 3, "Terran Barracks", true,
            {"terran_marine"}},
    };
    for (const auto& type : types) if (id == type.id) return &type;
    return nullptr;
}

inline const WorldBuildingType* worldBuildingType(BWAPI::UnitType native) {
    const auto* barracks = worldBuildingType("terran_barracks");
    return barracks->native == native ? barracks : nullptr;
}

inline bool worldCanProduce(const WorldBuildingType& building, const std::string& unitID) {
    for (const auto* id : building.trainable) if (unitID == id) return true;
    return false;
}
