#pragma once

#include "WorldStarcraftTypes.h"
#include <BWAPI.h>
#include <nlohmann/json.hpp>
#include <map>
#include <string>
#include <vector>

// Reports exact native tile/type/owner facts for bridge-owned construction
// intents. It never creates, removes, moves, or pays for a native building.
class WorldConstructionWatches {
    using json = nlohmann::json;
    struct Watch { std::string type; int x = -1, y = -1; std::string last;
        int lastRemaining = -1, lastProgressFrame = 0; };
public:
    bool watch(const json& payload, BWAPI::Game* game) {
        const std::string id = payload.value("intent_id", "");
        const std::string type = payload.value("building_type", "");
        const int x = payload.value("tile_x", -1), y = payload.value("tile_y", -1);
        if (id.empty() || id.size() > 128 || !worldBuildingType(type)
            || x < 0 || y < 0 || x >= game->mapWidth() || y >= game->mapHeight()) return false;
        auto found = watches_.find(id);
        if (found != watches_.end() && (found->second.type != type || found->second.x != x
            || found->second.y != y)) return false;
        watches_[id] = {type, x, y, "", -1, 0};
        return true;
    }
    void resetPublication() { for (auto& [id, watch] : watches_) watch.last.clear(); }
    std::vector<json> observe(BWAPI::Game* game) {
        std::vector<json> states;
        for (auto& [id, watch] : watches_) {
            const auto* building = worldBuildingType(watch.type);
            BWAPI::Unit match = nullptr;
            int matches = 0;
            for (auto unit : game->getAllUnits()) {
                if (!unit || !unit->exists() || !unit->getPlayer()
                    || unit->getPlayer()->getID() != 1 || unit->getType() != building->native) continue;
                const auto tile = unit->getTilePosition();
                if (tile.x != watch.x || tile.y != watch.y) continue;
                match = unit; ++matches;
            }
            const int remaining = matches == 1 ? match->getRemainingBuildTime() : 0;
            if (matches == 1 && !match->isCompleted()) {
                if (watch.lastRemaining != remaining || watch.lastProgressFrame == 0) {
                    watch.lastRemaining = remaining;
                    watch.lastProgressFrame = game->getFrameCount();
                }
            } else { watch.lastRemaining = -1; watch.lastProgressFrame = 0; }
            const bool paused = matches == 1 && !match->isCompleted()
                && game->getFrameCount() - watch.lastProgressFrame >= 36;
            json state = {{"intent_id", id}, {"type", watch.type}, {"owner", 1},
                {"tile_x", watch.x}, {"tile_y", watch.y},
                {"state", matches > 1 ? "ambiguous" : !match ? "absent"
                    : match->isCompleted() ? "completed" : paused ? "paused" : "incomplete"},
                {"native_id", matches == 1 ? std::to_string(match->getID()) : ""},
                {"remaining_frames", remaining},
                {"health", matches == 1 ? match->getHitPoints() : 0}};
            const std::string encoded = state.dump();
            if (watch.last != encoded) { watch.last = encoded; states.push_back(std::move(state)); }
        }
        return states;
    }
private:
    std::map<std::string, Watch> watches_;
};
