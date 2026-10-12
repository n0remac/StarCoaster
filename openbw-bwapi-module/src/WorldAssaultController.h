#pragma once

#include <BWAPI.h>
#include <climits>
#include <cstdlib>
#include <vector>

// Scenario policy. Native BWAPI orders, movement, target acquisition, and
// combat remain authoritative; the generic world adapter owns no target IDs.
class WorldAssaultController {
public:
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
};
