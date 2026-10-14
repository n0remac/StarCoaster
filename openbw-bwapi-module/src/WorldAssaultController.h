#pragma once

#include <BWAPI.h>
#include <algorithm>
#include <climits>
#include <cstdlib>
#include <string>
#include <utility>
#include <vector>

// Scenario policy. Native BWAPI orders, movement, target acquisition, and
// combat remain authoritative; the generic world adapter owns no target IDs.
class WorldAssaultController {
public:
    void configure(std::string objectiveID, std::string session = "") {
        if (session == session_ && objectiveID == objectiveID_) return;
        session_ = std::move(session);
        objectiveID_ = std::move(objectiveID);
        started_ = false;
        notBeforeFrame_ = 0;
    }
    bool start(int frame, int delayFrames) {
        if (objectiveID_.empty()) return false;
        if (started_) return true;
        started_ = true;
        notBeforeFrame_ = frame + std::max(0, std::min(600, delayFrames));
        return true;
    }
    bool active(int frame) const {
        return !objectiveID_.empty() && started_ && frame >= notBeforeFrame_;
    }
    const std::string& objectiveID() const { return objectiveID_; }

    void step(BWAPI::Game* game, BWAPI::Unit objective,
              const std::vector<BWAPI::Unit>& alternatives) const {
        if (!game || !game->self()) return;
        for (auto unit : game->getAllUnits()) {
            if (!unit || !unit->exists() || unit->getPlayer() != game->self()
                || unit->getType() != BWAPI::UnitTypes::Zerg_Zergling) continue;
            BWAPI::Unit target = objective && objective->exists() ? objective : nullptr;
            if (!target) {
                int best = INT_MAX;
                for (auto candidate : alternatives) {
                    if (!candidate || !candidate->exists() || candidate->getPlayer() == game->self()) continue;
                    const auto a = unit->getPosition(), b = candidate->getPosition();
                    const int distance = std::abs(a.x - b.x) + std::abs(a.y - b.y);
                    if (distance < best) { best = distance; target = candidate; }
                }
            }
            if (target && unit->getOrderTarget() != target && unit->getTarget() != target)
                unit->attack(target);
        }
    }
private:
    std::string objectiveID_;
    std::string session_;
    int notBeforeFrame_ = 0;
    bool started_ = false;
};
