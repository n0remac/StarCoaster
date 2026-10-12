#pragma once

#include <BWAPI.h>

#include <algorithm>
#include <map>
#include <string>
#include <tuple>
#include <vector>

// Static map actors receive the same logical IDs in both synchronized BWAPI
// player processes, even when their local BWAPI unit IDs differ. New runtime
// actor creation will require an explicit generation handshake later.
class WorldActorRegistry {
public:
    bool prepare(BWAPI::Game* game) {
        if (prepared_) return true;
        if (!game || game->getFrameCount() < 2) return false;
        std::vector<BWAPI::Unit> marines, zerglings;
        for (auto unit : game->getAllUnits()) {
            if (!unit || !unit->exists()) continue;
            if (unit->getType() == BWAPI::UnitTypes::Terran_Marine) marines.push_back(unit);
            else if (unit->getType() == BWAPI::UnitTypes::Zerg_Zergling) zerglings.push_back(unit);
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
};
