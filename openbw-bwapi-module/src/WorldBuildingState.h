#pragma once

#include "WorldStarcraftTypes.h"
#include <BWAPI.h>
#include <nlohmann/json.hpp>
#include <algorithm>

// Native owner participants publish one common building-state contract. All
// availability is anchored to BWAPI::Unit::canTrain on the owning player.
inline nlohmann::json worldBuildingAvailability(BWAPI::Game* game, BWAPI::Unit producer,
                                               const WorldBuildingType& building) {
    using json = nlohmann::json;
    json result = json::object();
    const auto owner = producer->getPlayer();
    for (const auto& unitID : building.trainable) {
        const auto* requested = worldUnitType(unitID);
        if (!requested) continue;
        const bool ready = producer->isCompleted() && producer->getHitPoints() > 0
            && producer->canTrain(requested->native);
        std::string reason = ready ? "ready" : "native_unavailable";
        std::string requirement;
        if (!ready) {
            if (!producer->isCompleted() || producer->getHitPoints() < 1)
                reason = "building_unavailable";
            else {
                for (const auto& [required, count] : requested->native.requiredUnits()) {
                    int completed = 0;
                    for (auto candidate : game->getAllUnits())
                        if (candidate && candidate->exists() && candidate->isCompleted()
                            && candidate->getPlayer() == owner
                            && candidate->getType() == required) ++completed;
                    if (completed < count) {
                        reason = "requires_building";
                        requirement = required.getName();
                        break;
                    }
                }
                if (reason == "native_unavailable") {
                    if (owner->minerals() < requested->native.mineralPrice())
                        reason = "insufficient_minerals";
                    else if (owner->gas() < requested->native.gasPrice())
                        reason = "insufficient_gas";
                    else if (owner->supplyUsed() + requested->native.supplyRequired()
                        > owner->supplyTotal()) reason = "supply_limit";
                    else if (producer->getTrainingQueue().size() >= 5)
                        reason = "queue_full";
                }
            }
        }
        result[unitID] = {{"ready", ready}, {"reason", reason},
                          {"requirement", requirement}};
    }
    return result;
}

inline nlohmann::json worldBuildingState(BWAPI::Game* game, BWAPI::Unit unit,
                                        const WorldBuildingType& building,
                                        const std::string& id, const std::string& proxyID) {
    using json = nlohmann::json;
    const auto availability = worldBuildingAvailability(game, unit, building);
    json commands = json::array();
    for (const auto& unitID : building.trainable) {
        const auto* requested = worldUnitType(unitID);
        if (!requested || commands.size() >= 9) continue;
        const auto& status = availability.at(unitID);
        commands.push_back({{"slot", commands.size()}, {"action", "unit.train"},
            {"unit_type", unitID}, {"label", requested->native.getName()},
            {"ready", status.at("ready")}, {"reason", status.at("reason")},
            {"requirement", status.at("requirement")}});
    }
    const auto owner = unit->getPlayer();
    json state = {{"id", id}, {"native_id", proxyID}, {"owner", owner->getID()},
        {"race", owner->getRace().getName()}, {"completed", unit->isCompleted()},
        {"health", unit->getHitPoints()}, {"max_health", unit->getType().maxHitPoints()},
        {"queue", unit->getTrainingQueue().size()},
        {"remaining_frames", unit->getRemainingTrainTime()},
        {"minerals", owner->minerals()}, {"gas", owner->gas()},
        {"availability", availability}, {"commands", commands},
        {"supply_used", owner->supplyUsed()}, {"supply_total", owner->supplyTotal()}};
    if (unit->getType().producesLarva()) {
        state["larva_count"] = unit->getLarva().size();
        int eggs = 0, remaining = 0;
        for (auto candidate : game->getAllUnits()) {
            if (candidate && candidate->exists() && candidate->getPlayer() == owner
                && candidate->getType() == BWAPI::UnitTypes::Zerg_Egg
                && candidate->getHatchery() == unit) {
                ++eggs;
                remaining = std::max(remaining, candidate->getRemainingBuildTime());
            }
        }
        state["morph_count"] = eggs;
        state["morph_remaining_frames"] = remaining;
    }
    if (unit->getType().supplyProvided() > 0)
        state["supply_provided"] = unit->getType().supplyProvided();
    return state;
}
