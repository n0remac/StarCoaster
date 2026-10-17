#pragma once

#include <BWAPI.h>
#include <cerrno>
#include <climits>
#include <cstdlib>

// The two native participants receive the same scenario starting resources.
// OpenBW remains the only authority for later spending and supply accounting.
inline bool applyWorldProductionFixture(BWAPI::Game* game) {
    const auto configured = [](const char* name, int& amount) {
        const char* value = std::getenv(name);
        if (!value || !*value) return false;
        char* end = nullptr;
        errno = 0;
        const long parsed = std::strtol(value, &end, 10);
        if (errno || !end || *end || parsed < 0 || parsed > 100000) return false;
        amount = static_cast<int>(parsed);
        return true;
    };
    int minerals = 0, gas = 0;
    const bool hasMinerals = configured("BRIDGE_TERRAN_STARTING_MINERALS", minerals);
    const bool hasGas = configured("BRIDGE_TERRAN_STARTING_GAS", gas);
    if (!hasMinerals && !hasGas) return true;
    for (auto player : game->getPlayers()) {
        if (!player || player->getID() != 1 || player->getRace() != BWAPI::Races::Terran) continue;
        if (hasMinerals) player->setMinerals(minerals);
        if (hasGas) player->setGas(gas);
        return true;
    }
    return false;
}
