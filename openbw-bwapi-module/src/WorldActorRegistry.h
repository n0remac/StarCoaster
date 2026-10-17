#pragma once

#include <BWAPI.h>
#include "WorldStarcraftTypes.h"

#include <algorithm>
#include <cstdint>
#include <map>
#include <set>
#include <string>
#include <tuple>
#include <vector>

// Static map actors retain their v0.2 IDs. Runtime actors are registered from
// native creation events with an explicit publisher token and creation frame.
class WorldActorRegistry {
public:
    struct RuntimeActor {
        int canonical = 0;
        BWAPI::Unit unit = nullptr;
        uint64_t generation = 0;
        int creationFrame = 0;
    };
    bool prepare(BWAPI::Game* game, const std::set<int>& runtimeCandidates = {}) {
        if (prepared_) return true;
        if (!game || game->getFrameCount() < 2) return false;
        std::vector<BWAPI::Unit> marines, zerglings;
        for (auto unit : game->getAllUnits()) {
            if (!unit || !unit->exists() || runtimeCandidates.count(unit->getID())) continue;
            const auto* type = worldUnitType(unit->getType());
            if (!type) continue;
            // Preserve the original positional identity groups for saved games.
            if (std::string(type->id) == "terran_marine") marines.push_back(unit);
            else if (std::string(type->id) == "zerg_zergling") zerglings.push_back(unit);
        }
        const auto byPosition = [](BWAPI::Unit a, BWAPI::Unit b) {
            const auto x = a->getPosition(), y = b->getPosition();
            return std::tie(x.x, x.y) < std::tie(y.x, y.y);
        };
        std::sort(marines.begin(), marines.end(), byPosition);
        std::sort(zerglings.begin(), zerglings.end(), byPosition);
        auto assign = [&](const std::vector<BWAPI::Unit>& group, int base) {
            for (size_t i = 0; i < group.size(); ++i) {
                if (i > 0 && group[i]->getPosition() == group[i - 1]->getPosition()) return false;
                const int canonical = base + static_cast<int>(i);
                canonicalToUnit_[canonical] = group[i];
                localToCanonical_[group[i]->getID()] = canonical;
            }
            return true;
        };
        if (!assign(marines, 1000) || !assign(zerglings, 2000)) {
            canonicalToUnit_.clear(); localToCanonical_.clear();
            return false;
        }
        prepared_ = true;
        return true;
    }
    std::string id(BWAPI::Unit unit) const {
        if (!unit) return "";
        const auto found = localToCanonical_.find(unit->getID());
        return found == localToCanonical_.end() ? "" : "openbw:" + std::to_string(found->second);
    }
    bool known(BWAPI::Unit unit) const {
        return unit && localToCanonical_.count(unit->getID()) != 0;
    }
    bool registerRuntime(BWAPI::Unit unit, int canonical, uint64_t generation, int creationFrame) {
        if (!prepared_ || !unit || !unit->exists() || canonical < 3000 || generation == 0
            || creationFrame < 1 || known(unit) || canonicalToUnit_.count(canonical)
            || !unit->isCompleted() || !worldUnitType(unit->getType())) return false;
        canonicalToUnit_[canonical] = unit;
        localToCanonical_[unit->getID()] = canonical;
        runtime_[canonical] = {canonical, unit, generation, creationFrame};
        return true;
    }
    bool forget(BWAPI::Unit unit) {
        if (!unit) return false;
        const auto found = localToCanonical_.find(unit->getID());
        if (found == localToCanonical_.end()) return false;
        const int canonical = found->second;
        localToCanonical_.erase(found);
        canonicalToUnit_.erase(canonical);
        return runtime_.erase(canonical) != 0;
    }
    const std::map<int, RuntimeActor>& runtime() const { return runtime_; }
    BWAPI::Unit lookup(const std::string& id) const {
        if (id.compare(0, 7, "openbw:") != 0) return nullptr;
        try {
            const int numeric = std::stoi(id.substr(7));
            const auto found = canonicalToUnit_.find(numeric);
            return found == canonicalToUnit_.end() ? nullptr : found->second;
        } catch (...) { return nullptr; }
    }
    bool prepared() const { return prepared_; }
    size_t actors() const { return canonicalToUnit_.size(); }
private:
    bool prepared_ = false;
    std::map<int, BWAPI::Unit> canonicalToUnit_;
    std::map<int, int> localToCanonical_;
    std::map<int, RuntimeActor> runtime_;
};
