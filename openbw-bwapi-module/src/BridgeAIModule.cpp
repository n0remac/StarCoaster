#include "WorldAdapter.h"
#include "WorldUnitController.h"
#include "BridgePerformance.h"

#include <BWAPI.h>
#include <chrono>
#include <algorithm>
#include <array>
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
        perfEnabled_ = std::getenv("STARCOASTER_PERF_DIR") != nullptr
            || std::getenv("STARCOASTER_PERF_BASELINE_DIR") != nullptr;
        perfWindowNS_ = bridge_perf::nowNS();
    }

    void onFrame() override {
        const auto started = perfEnabled_ ? bridge_perf::nowNS() : 0;
        // OpenBW runs unpaced without its UI. Match the configured simulation cadence.
        if (frameDelayMs_ > 0)
            std::this_thread::sleep_for(std::chrono::milliseconds(frameDelayMs_));
        const auto afterSleep = perfEnabled_ ? bridge_perf::nowNS() : 0;
        auto* game = BWAPI::Broodwar.operator->();
        if (!game || game->isReplay() || !game->self()) return;
        if (controller_) worldUnitController_.onFrame(game);
        else worldAdapter_.onFrame(game);
        if (!perfEnabled_) return;
        const auto finished = bridge_perf::nowNS();
        const auto workUS = (finished - afterSleep) / 1000;
        perfFrames_++;
        perfWorkUS_ += workUS;
        if (perfWorkSamples_ < perfWorkWindow_.size()) perfWorkWindow_[perfWorkSamples_++] = workUS;
        perfSleepUS_ += (afterSleep - started) / 1000;
        perfMaxWorkUS_ = std::max(perfMaxWorkUS_, workUS);
        if (workUS > 42000 - frameDelayMs_ * 1000) perfOverruns_++;
        if (perfLastFrameNS_ != 0)
            perfMaxDelayUS_ = std::max(perfMaxDelayUS_, (started - perfLastFrameNS_) / 1000);
        perfLastFrameNS_ = started;
        if (finished - perfWindowNS_ >= 1000000000LL) {
            std::sort(perfWorkWindow_.begin(), perfWorkWindow_.begin() + perfWorkSamples_);
            const auto at = [this](double fraction) {
                return perfWorkSamples_ ? perfWorkWindow_[static_cast<size_t>((perfWorkSamples_ - 1) * fraction)] : 0LL;
            };
            bridge_perf::frame(controller_ ? "controller" : "publisher", game->getFrameCount(), perfFrames_,
                finished - perfWindowNS_, perfWorkUS_, perfMaxWorkUS_, perfSleepUS_, perfOverruns_, perfMaxDelayUS_,
                at(.50), at(.95), at(.99));
            perfWindowNS_ = finished;
            perfFrames_ = perfOverruns_ = 0;
            perfWorkUS_ = perfMaxWorkUS_ = perfSleepUS_ = perfMaxDelayUS_ = 0;
            perfWorkSamples_ = 0;
        }
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
    bool perfEnabled_ = false;
    long long perfWindowNS_ = 0, perfLastFrameNS_ = 0;
    long long perfWorkUS_ = 0, perfMaxWorkUS_ = 0, perfSleepUS_ = 0, perfMaxDelayUS_ = 0;
    int perfFrames_ = 0, perfOverruns_ = 0;
    std::array<long long, 256> perfWorkWindow_{};
    size_t perfWorkSamples_ = 0;
};

}  // namespace

extern "C" void gameInit(BWAPI::Game* game) { BWAPI::BroodwarPtr = game; }
extern "C" BWAPI::AIModule* newAIModule() { return new BridgeAIModule(); }
