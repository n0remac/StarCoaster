#pragma once

#include <BWAPI.h>
#include <cerrno>
#include <climits>
#include <cstdlib>

// The two native participants receive the same scenario starting resources.
// OpenBW remains the only authority for later spending and supply accounting.
inline bool applyWorldProductionFixture(BWAPI::Game* game) {
    const char* value = std::getenv("BRIDGE_TERRAN_STARTING_MINERALS");
    if (!value || !*value) return true;
    char* end = nullptr;
    errno = 0;
    const long minerals = std::strtol(value, &end, 10);
    if (errno || !end || *end || minerals < 0 || minerals > 100000) return true;
    for (auto player : game->getPlayers()) {
        if (!player || player->getID() != 1 || player->getRace() != BWAPI::Races::Terran) continue;
        player->setMinerals(static_cast<int>(minerals));
        return true;
    }
    return false;
}
