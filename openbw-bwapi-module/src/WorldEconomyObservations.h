#pragma once

#include "WorldStarcraftTypes.h"
#include <BWAPI.h>
#include <nlohmann/json.hpp>
#include <cstdlib>
#include <fstream>
#include <map>
#include <string>
#include <vector>

// The authored site fixes identity; the observed BWAPI unit supplies every
// running quantity and native ID. This cache survives bridge socket reconnects
// because it belongs to the continuing OpenBW participant.
class WorldEconomyObservations {
public:
    using json = nlohmann::json;
    struct Site {
        std::string id;
        int x = 0, y = 0;
        int width = 0, height = 0;
        std::string kind;
        int nativeID = -1;
        std::string nativeType;
        int generation = 0;
    };

    WorldEconomyObservations() {
        const char* config = std::getenv("BRIDGE_SCENARIO_CONFIG");
        if (!config || !*config) return;
        std::ifstream input(config);
        if (!input) return;
        try {
            const json scenario = json::parse(input);
            if (!scenario.contains("economy") || scenario.at("economy").value("mode", "") != "finite") return;
            const auto size = scenario.at("park_size");
            const int offsetX = (256 - size.at(0).get<int>()) / 2;
            const int offsetY = (256 - size.at(1).get<int>()) / 2;
            for (const auto& entity : scenario.at("economy").at("starting_entities")) {
                const std::string type = entity.at("type").get<std::string>();
                const auto* resource = worldUnitType(type);
                if (!resource || std::string(resource->ownership) != "neutral") continue;
                const int width = type == "mineral_field" ? 2 : 4;
                const int height = type == "mineral_field" ? 1 : 2;
                const auto tile = entity.at("tile");
                sites_.push_back({entity.at("id").get<std::string>(),
                    (tile.at(0).get<int>() + offsetX) * 32 + width * 16,
                    (tile.at(1).get<int>() + offsetY) * 32 + height * 16,
                    width, height, type});
            }
        } catch (...) { sites_.clear(); }
    }

    bool enabled() const { return !sites_.empty(); }
    json bindingFor(BWAPI::Unit unit) const {
        if (!unit) return nullptr;
        for (const auto& site : sites_)
            if (site.nativeID == unit->getID() && site.nativeType.size())
                return {{"site_id", site.id}, {"generation", site.generation},
                    {"native_id", std::to_string(site.nativeID)}};
        return nullptr;
    }
    std::vector<json> observe(BWAPI::Game* game) {
        std::vector<json> states;
        if (!game) return states;
        for (auto& site : sites_) {
            BWAPI::Unit match = nullptr;
            int matches = 0;
            for (auto unit : game->getAllUnits()) {
                if (!unit || !unit->exists() || unit->getPosition().x != site.x
                    || unit->getPosition().y != site.y) continue;
                const auto native = unit->getType();
                if (native != BWAPI::UnitTypes::Resource_Mineral_Field
                    && native != BWAPI::UnitTypes::Resource_Vespene_Geyser
                    && native != BWAPI::UnitTypes::Terran_Refinery) continue;
                match = unit;
                ++matches;
            }
            if (matches > 1) continue; // Ambiguity is never resolved by proximity.
            const int nativeID = match ? match->getID() : -1;
            const std::string type = match ? (match->getType() == BWAPI::UnitTypes::Terran_Refinery
                ? "terran_refinery" : site.kind) : "";
            if (nativeID != site.nativeID || type != site.nativeType) {
                ++site.generation;
                site.nativeID = nativeID;
                site.nativeType = type;
            }
            if (!site.generation) site.generation = 1;
            const int owner = match && match->getPlayer() && match->getPlayer()->getID() >= 0
                ? match->getPlayer()->getID() : 11;
            states.push_back({{"site_id", site.id}, {"generation", site.generation},
                {"native_id", match ? std::to_string(nativeID) : ""},
                {"type", type}, {"owner", owner}, {"x", site.x}, {"y", site.y},
                {"amount", match ? match->getResources() : 0},
                {"lifecycle", !match ? "absent" : type == "terran_refinery" ? "refinery" : "deposit"}});
        }
        return states;
    }
private:
    std::vector<Site> sites_;
};
