#include "WorldAssaultController.h"

#undef NDEBUG
#include <cassert>
#include <type_traits>

static_assert(std::is_same_v<decltype(&BWAPI::Game::hasUnitTypePath),
    bool (BWAPI::Game::*)(BWAPI::UnitType, BWAPI::Position, BWAPI::Position)>);

int main() {
    WorldAssaultController controller;
    assert(!controller.active(100)); // Generic world sessions have no assault policy.
    assert(!controller.start(100, 0));
    controller.configure("openrct2:ride:0#1");
    assert(!controller.active(100));
    assert(controller.start(100, 144));
    assert(!controller.active(243));
    assert(controller.active(244));
    controller.configure("openrct2:ride:0#1"); // same-session resnapshot
    assert(controller.start(500, 144));
    assert(controller.active(500)); // original delay was not restarted
    controller.configure("openrct2:ride:0#1", "new-session");
    assert(!controller.active(500));
    controller.configure(""); // A new generic session retires the old encounter.
    assert(!controller.active(1000));
    controller.configure("", "park-session", true);
    assert(controller.start(1000, 0));
    assert(controller.active(1000));
    controller.configure("", "park-session", true); // same-session snapshot preserves policy
    assert(controller.active(1000));
    const auto rallies = WorldAssaultController::interiorRallies(64, 48, BWAPI::Position(96, 96));
    assert(rallies.size() > 1);
    assert(rallies.front().x < 64 * 16 && rallies.front().y < 48 * 16);
    controller.setWaveDestination(3001, BWAPI::Position(800, 700));
    assert(controller.shouldIssueWaveRally(3001, BWAPI::Position(96, 96), BWAPI::Position(0, 0), false, true));
    assert(!controller.shouldIssueWaveRally(3001, BWAPI::Position(128, 128), BWAPI::Position(0, 0), false, true));
    assert(!controller.shouldIssueWaveRally(3001, BWAPI::Position(128, 128), BWAPI::Position(0, 0), true, false));
    assert(controller.shouldIssueWaveRally(3001, BWAPI::Position(128, 128), BWAPI::Position(0, 0), true, true));
    assert(controller.shouldIssueWaveRally(3001, BWAPI::Position(128, 128), BWAPI::Position(0, 0), true, true));
    assert(!controller.shouldIssueWaveRally(3001, BWAPI::Position(800, 700), BWAPI::Position(0, 0), true, true));
    controller.navigationChanged();
    assert(!controller.shouldIssueWaveRally(3001, BWAPI::Position(128, 128), BWAPI::Position(0, 0), false, true));
    assert(!controller.shouldIssueWaveRally(3001, BWAPI::Position(128, 128), BWAPI::Position(0, 0), true, true));
    assert(!controller.shouldIssueWaveRally(3001, BWAPI::Position(128, 128), BWAPI::Position(0, 0), true, false));
    controller.navigationChanged();
    assert(controller.shouldIssueWaveRally(3001, BWAPI::Position(128, 128), BWAPI::Position(0, 0), true, true));
    assert(controller.shouldIssueWaveRally(3001, BWAPI::Position(128, 128), BWAPI::Position(0, 0), true, true));
    assert(!controller.shouldIssueWaveRally(3001, BWAPI::Position(128, 128), BWAPI::Position(0, 0), true, true));
    assert(controller.rallyFor(3001, 64, 48, BWAPI::Position(96, 96)) == BWAPI::Position(800, 700));
    assert(controller.rallyFor(3001, 64, 48, BWAPI::Position(800, 700)) == BWAPI::Position(800, 700));
    const auto fallback = controller.rallyFor(3002, 64, 48, BWAPI::Position(96, 96));
    assert(controller.rallyFor(3002, 64, 48, fallback) == fallback);
    controller.configure("", "next-park", true);
    assert(controller.rallyFor(3001, 64, 48, BWAPI::Position(96, 96)) != BWAPI::Position(800, 700));
    controller.configure("", "colony-park", true, true);
    assert(controller.baseProduction());
    controller.setWaveDestination(3003, BWAPI::Position(800, 700));
    assert(!controller.shouldIssueWaveRally(3003, BWAPI::Position(96, 96),
        BWAPI::Position(0, 0), false, true)); // engaged units keep fighting
    assert(controller.shouldIssueWaveRally(3003, BWAPI::Position(96, 96),
        BWAPI::Position(0, 0), true, true));
}
