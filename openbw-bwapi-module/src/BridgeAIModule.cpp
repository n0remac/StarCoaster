#include "WorldAdapter.h"
#include "WorldUnitController.h"

#include <BWAPI.h>
#include <chrono>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <thread>

namespace {

int frameDelay() {
    const char* value = std::getenv("BRIDGE_FRAME_MS");
    if (!value || !*value) return 42;
    char* end = nullptr;
    const long delay = std::strtol(value, &end, 10);
    return end && !*end && delay >= 0 && delay <= 1000 ? static_cast<int>(delay) : 42;
}

class BridgeAIModule final : public BWAPI::AIModule {
public:
    void onStart() override {
        const char* scenario = std::getenv("BRIDGE_SCENARIO");
        if (scenario && std::strcmp(scenario, "world") != 0)
            std::cerr << "[bridge] unsupported BRIDGE_SCENARIO=" << scenario << std::endl;
        auto* game = BWAPI::Broodwar.operator->();
        if (!game || game->isReplay() || !game->self()) {
            std::cerr << "[bridge] no active player" << std::endl;
            return;
        }
        // Both native roles observe the full map; BWAPI still enforces order ownership.
        game->enableFlag(BWAPI::Flag::CompleteMapInformation);
        const char* role = std::getenv("BRIDGE_WORLD_ROLE");
        controller_ = role && std::strcmp(role, "controller") == 0;
        frameDelayMs_ = frameDelay();
    }

    void onFrame() override {
        // OpenBW runs unpaced without its UI. Match the configured simulation cadence.
        if (frameDelayMs_ > 0)
            std::this_thread::sleep_for(std::chrono::milliseconds(frameDelayMs_));
        auto* game = BWAPI::Broodwar.operator->();
        if (!game || game->isReplay() || !game->self()) return;
        if (controller_) worldUnitController_.onFrame(game);
        else worldAdapter_.onFrame(game);
    }

    void onUnitCreate(BWAPI::Unit unit) override {
        const int frame = BWAPI::Broodwar->getFrameCount();
        if (controller_) worldUnitController_.onUnitCreate(unit, frame);
        else worldAdapter_.onUnitCreate(unit, frame);
    }

    void onUnitDestroy(BWAPI::Unit unit) override {
        if (controller_) worldUnitController_.onUnitDestroy(unit);
        else worldAdapter_.onUnitDestroy(unit, BWAPI::Broodwar->getFrameCount());
    }

private:
    WorldAdapter worldAdapter_;
    WorldUnitController worldUnitController_;
    bool controller_ = false;
    int frameDelayMs_ = 42;
};

}  // namespace

extern "C" void gameInit(BWAPI::Game* game) { BWAPI::BroodwarPtr = game; }
extern "C" BWAPI::AIModule* newAIModule() { return new BridgeAIModule(); }
