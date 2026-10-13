#include "WorldNavigation.h"
#include "WorldSpawnPlacement.h"

#include <cassert>
#include <iostream>

using namespace starcoaster;

int main() {
    DesiredWorld world;
    world.width = world.height = 8;
    auto ride = parseEntity({{"id", "ride#1"}, {"source", "openrct2"}, {"source_id", "ride:1"},
        {"kind", "ride"}, {"destructible", true},
        {"combat", {{"targetable", true}, {"health", 100}}},
        {"collision", {{"blocks", true}}},
        {"geometry", {{"rects", Json::array({{{"x", 32}, {"y", 32},
            {"width", 96}, {"height", 96}}})}}}}, 8, 8);
    world.entities[ride.id] = ride;
    auto scenery = ride;
    scenery.id = "scenery#1";
    scenery.rectangles = {{96, 96, 32, 32}};
    world.entities[scenery.id] = scenery;
    NavigationAdapter navigation;
    navigation.replace(world);
    assert(navigation.objects() == 2);
    assert(navigation.blocked(64, 64, 8));
    assert(navigation.blocked(100, 100));
    assert(!navigation.blocked(160, 160));
    assert(navigation.remove("ride#1"));
    assert(!navigation.blocked(64, 64));
    assert(navigation.blocked(100, 100));
    assert(navigation.remove("scenery#1"));
    assert(!navigation.blocked(100, 100));
    assert(!navigation.remove("scenery#1"));
    const auto first = compactSpawnPosition(160, 160, 0);
    const auto second = compactSpawnPosition(160, 160, 1);
    assert(first.x == 160 && first.y == 160 && second.x == 192 && second.y == 160);
    assert(validSpawnPlacement(navigation, first.x, first.y, 8, 8, 9, 9, {}));
    assert(!validSpawnPlacement(navigation, first.x, first.y, 8, 8, 9, 9, {{152, 152, 16, 16}}));
    assert(!validSpawnPlacement(navigation, 252, 160, 8, 8, 9, 9, {}));
    navigation.upsert("new-wall", {{152, 152, 16, 16}});
    assert(!validSpawnPlacement(navigation, first.x, first.y, 8, 8, 9, 9, {}));
    std::cout << "world navigation metadata tests passed\n";
}
