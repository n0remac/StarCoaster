#pragma once

#include "WorldNavigation.h"

#include <array>
#include <vector>

namespace starcoaster {

struct SpawnPoint { int x = 0; int y = 0; };

inline SpawnPoint compactSpawnPosition(int x, int y, int index) {
    static constexpr std::array<SpawnPoint, 5> offsets = {{{0, 0}, {32, 0}, {-32, 0}, {0, 32}, {0, -32}}};
    if (index < 0 || index >= static_cast<int>(offsets.size())) return {-1, -1};
    return {x + offsets[index].x, y + offsets[index].y};
}

inline bool validSpawnPlacement(const NavigationAdapter& navigation, int x, int y,
                                int mapWidth, int mapHeight, int halfWidth, int halfHeight,
                                const std::vector<Rect>& occupied) {
    if (halfWidth < 1 || halfHeight < 1 || x < halfWidth || y < halfHeight
        || x + halfWidth >= mapWidth * 32 || y + halfHeight >= mapHeight * 32)
        return false;
    const int clearance = std::max(halfWidth, halfHeight);
    if (navigation.blocked(x, y, clearance)) return false;
    for (const auto& other : occupied)
        if (x - halfWidth < other.x + other.width && x + halfWidth > other.x
            && y - halfHeight < other.y + other.height && y + halfHeight > other.y)
            return false;
    return true;
}

} // namespace starcoaster
