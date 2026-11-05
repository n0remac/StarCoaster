#pragma once

#include <BWAPI.h>
#include <cstdlib>
#include <iostream>
#include <string>

// Test-only native orders and observations. Nothing here enters the player
// command route; the fixture is enabled only by its explicit live-test flag.
class WorldEconomyE0Probe {
public:
    explicit WorldEconomyE0Probe(bool controller) : controller_(controller) {}

    void onFrame(BWAPI::Game* game, bool mapped, const std::string& mask = "") {
        if (!std::getenv("BRIDGE_TEST_ECONOMY_E0") || !game || game->getFrameCount() < 120)
            return;
        const int frame = game->getFrameCount();
        BWAPI::Unit center = nullptr, miner = nullptr, builder = nullptr;
        BWAPI::Unit mineral = nullptr, geyser = nullptr, depot = nullptr;
        BWAPI::Unit cancelled = nullptr, refinery = nullptr;
        for (auto unit : game->getAllUnits()) {
            if (!unit || !unit->exists()) continue;
            const auto type = unit->getType();
            const auto tile = unit->getTilePosition();
            if (type == BWAPI::UnitTypes::Terran_Command_Center) center = unit;
            if (type == BWAPI::UnitTypes::Terran_SCV) {
                if (!miner || unit->getID() < miner->getID()) miner = unit;
                if (!builder || unit->getID() > builder->getID()) builder = unit;
            }
            if (type == BWAPI::UnitTypes::Resource_Mineral_Field
                && (!mineral || unit->getID() < mineral->getID())) mineral = unit;
            if (type == BWAPI::UnitTypes::Resource_Vespene_Geyser) geyser = unit;
            if (type == BWAPI::UnitTypes::Terran_Supply_Depot) {
                if (tile.x == depotX_ && tile.y == depotY_) depot = unit;
                if (tile.x == cancelX_ && tile.y == cancelY_) cancelled = unit;
            }
            if (type == BWAPI::UnitTypes::Terran_Refinery) refinery = unit;
        }
        auto owner = game->getPlayer(1);
        if (!owner || !center || !miner || !builder || !mineral || (!geyser && !refinery)) {
            if (frame % 120 == 0) event(game, "missing_fixture", "");
            return;
        }
        if (!initial_ && mapped) {
            initial_ = true;
            initialMinerals_ = owner->minerals();
            lastMinerals_ = initialMinerals_;
            lastGas_ = owner->gas();
            event(game, "initial", "mask=" + mask + " center=" + std::to_string(center->getID())
                + " center_owner=" + std::to_string(center->getPlayer()->getID())
                + " miner=" + std::to_string(miner->getID())
                + " builder=" + std::to_string(builder->getID())
                + " mineral=" + std::to_string(mineral->getID())
                + " mineral_owner=" + std::to_string(mineral->getPlayer()->getID())
                + " mineral_amount=" + std::to_string(mineral->getResources())
                + " geyser=" + std::to_string(geyser->getID())
                + " geyser_owner=" + std::to_string(geyser->getPlayer()->getID())
                + " geyser_amount=" + std::to_string(geyser->getResources())
                + " supply=" + std::to_string(owner->supplyUsed()) + "/"
                + std::to_string(owner->supplyTotal()));
        }
        if (!initial_) return;
        if (frame % 24 == 0) {
            event(game, "state", "miner_pos=" + std::to_string(miner->getPosition().x)
                + "," + std::to_string(miner->getPosition().y)
                + " mineral_amount=" + std::to_string(mineral->getResources())
                + " cargo_m=" + std::to_string(miner->isCarryingMinerals())
                + " cargo_g=" + std::to_string(miner->isCarryingGas())
                + " depot=" + state(depot) + " cancelled=" + state(cancelled)
                + " refinery=" + state(refinery));
        }
        if (owner->minerals() > lastMinerals_ && stage_ <= 1) {
            ++deliveries_;
            event(game, "mineral_delivery", "count=" + std::to_string(deliveries_)
                + " from=" + std::to_string(lastMinerals_) + " to="
                + std::to_string(owner->minerals()) + " remaining="
                + std::to_string(mineral->getResources()));
        }
        if (owner->gas() > lastGas_)
            event(game, "gas_delivery", "from=" + std::to_string(lastGas_) + " to="
                + std::to_string(owner->gas()) + " remaining="
                + std::to_string(refinery ? refinery->getResources() : geyser->getResources()));
        lastMinerals_ = owner->minerals(); lastGas_ = owner->gas();
        if (!controller_) return;
        if (stage_ == 0) {
            stage_ = 1;
            order(game, "gather_mineral", miner->gather(mineral));
        }
        if (stage_ == 1 && deliveries_ >= 2) {
            stage_ = 2;
            miner->stop();
            if (!chooseSite(game, builder, 135, 104, depotX_, depotY_)) {
                stage_ = 99; event(game, "no_depot_site", ""); return;
            }
            event(game, "selected_depot_site", "x=" + std::to_string(depotX_)
                + " y=" + std::to_string(depotY_));
            order(game, "approach_depot", builder->move(
                {(depotX_ + 1) * 32 + 16, depotY_ * 32 + 16}));
        }
        if (stage_ == 2 && game->isExplored(depotX_, depotY_)) {
            const bool open = game->canBuildHere({depotX_, depotY_},
                BWAPI::UnitTypes::Terran_Supply_Depot, builder, true);
            if (!open) return;
            int staticBuildable = 0, candidateCount = 0, explored = 0;
            std::string firstCandidate = "none";
            for (int y = 104; y <= 151; ++y)
                for (int x = 104; x <= 151; ++x) {
                    if (game->isBuildable(x, y)) ++staticBuildable;
                    if (game->isExplored(x, y)) ++explored;
                    if (game->canBuildHere({x, y}, BWAPI::UnitTypes::Terran_Supply_Depot,
                                           builder, false)) {
                        ++candidateCount;
                        if (firstCandidate == "none")
                            firstCandidate = std::to_string(x) + "," + std::to_string(y);
                    }
                }
            event(game, "depot_site", "x=" + std::to_string(depotX_)
                + " y=" + std::to_string(depotY_)
                + " explored=1 can_build=" + std::to_string(open)
                + " walk=" + std::to_string(game->isWalkable(135 * 4, 104 * 4))
                + " static_buildable=" + std::to_string(staticBuildable)
                + " explored_tiles=" + std::to_string(explored)
                + " candidate_count=" + std::to_string(candidateCount)
                + " first_candidate=" + firstCandidate
                + " tile_buildable=" + std::to_string(game->isBuildable(135, 104))
                + "," + std::to_string(game->isBuildable(136, 104))
                + "," + std::to_string(game->isBuildable(137, 104))
                + "," + std::to_string(game->isBuildable(135, 105))
                + "," + std::to_string(game->isBuildable(136, 105))
                + "," + std::to_string(game->isBuildable(137, 105)));
            stage_ = 3;
            order(game, "build_depot", builder->build(
                BWAPI::UnitTypes::Terran_Supply_Depot, {depotX_, depotY_}));
        }
        if (stage_ == 3 && depot && !depot->isCompleted()
            && depot->getRemainingBuildTime() < 500) {
            stage_ = 4; pauseFrame_ = frame;
            order(game, "interrupt_depot", builder->stop());
        }
        if (stage_ == 4 && frame >= pauseFrame_ + 60) {
            stage_ = 5;
            order(game, "resume_depot", builder->rightClick(depot));
        }
        if (stage_ == 5 && depot && depot->isCompleted()) {
            stage_ = 6;
            event(game, "depot_complete", "native=" + std::to_string(depot->getID())
                + " supply=" + std::to_string(owner->supplyTotal()));
            if (!chooseSite(game, builder, depotX_ + 6, depotY_, cancelX_, cancelY_)) {
                stage_ = 99; event(game, "no_cancel_site", ""); return;
            }
            event(game, "selected_cancel_site", "x=" + std::to_string(cancelX_)
                + " y=" + std::to_string(cancelY_));
            approachFrame_ = frame;
        }
        if (stage_ == 6 && !approachIssued_ && frame >= approachFrame_ + 8) {
            const bool accepted = builder->move(
                {(cancelX_ + 1) * 32 + 16, cancelY_ * 32 + 16});
            order(game, "approach_cancel", accepted);
            if (accepted) { approachIssued_ = true; approachFrame_ = frame; }
        }
        if (stage_ == 6 && approachIssued_ && frame >= approachFrame_ + 8
            && !builder->isMoving() && game->canBuildHere({cancelX_, cancelY_},
                            BWAPI::UnitTypes::Terran_Supply_Depot, builder, true)) {
            stage_ = 7;
            order(game, "build_cancel_depot", builder->build(
                BWAPI::UnitTypes::Terran_Supply_Depot, {cancelX_, cancelY_}));
        }
        if (stage_ == 7 && cancelled && !cancelled->isCompleted()) {
            stage_ = 8;
            event(game, "cancel_target", "native=" + std::to_string(cancelled->getID())
                + " remaining=" + std::to_string(cancelled->getRemainingBuildTime()));
            order(game, "cancel_depot", cancelled->cancelConstruction());
        }
        if (stage_ == 8 && !cancelled) {
            stage_ = 9;
            event(game, "cancel_removed", "");
            approachIssued_ = false; approachFrame_ = frame;
        }
        if (stage_ == 9 && !approachIssued_ && frame >= approachFrame_ + 8) {
            const bool accepted = builder->move({131 * 32, 105 * 32});
            order(game, "approach_refinery", accepted);
            if (accepted) { approachIssued_ = true; approachFrame_ = frame; }
        }
        if (stage_ == 9 && approachIssued_ && frame >= approachFrame_ + 8
            && !builder->isMoving() && game->isExplored(130, 104)) {
            stage_ = 10;
            const bool open = game->canBuildHere({130, 104},
                BWAPI::UnitTypes::Terran_Refinery, builder, true);
            event(game, "refinery_site", "explored=1 can_build=" + std::to_string(open)
                + " geyser=" + std::to_string(geyser->getID()));
            order(game, "build_refinery", builder->build(
                BWAPI::UnitTypes::Terran_Refinery, {130, 104}));
        }
        if (stage_ == 10 && refinery && refinery->isCompleted()) {
            stage_ = 11;
            event(game, "refinery_complete", "native=" + std::to_string(refinery->getID())
                + " amount=" + std::to_string(refinery->getResources()));
            order(game, "gather_gas", miner->gather(refinery));
        }
        if (stage_ == 11 && owner->gas() > 0) {
            stage_ = 12;
            event(game, "gas_complete", "refinery=" + std::to_string(refinery->getID()));
            order(game, "stop_gas_worker", miner->stop());
            destructionFrame_ = frame;
        }
        if (stage_ == 12 && frame >= destructionFrame_ + 16 && refinery) {
            stage_ = 13;
            const int native = refinery->getID();
            game->killUnit(refinery);
            event(game, "kill_refinery", "native=" + std::to_string(native));
        }
        if (stage_ == 13 && geyser && !refinery) {
            stage_ = 14;
            event(game, "geyser_restored", "native=" + std::to_string(geyser->getID())
                + " owner=" + std::to_string(geyser->getPlayer()->getID())
                + " amount=" + std::to_string(geyser->getResources()));
        }
    }
private:
    static bool chooseSite(BWAPI::Game* game, BWAPI::Unit builder, int wantedX, int wantedY,
                           int& selectedX, int& selectedY) {
        int best = 1 << 30;
        for (int y = 104; y <= 151; ++y)
            for (int x = 104; x <= 151; ++x) {
                if (!game->canBuildHere({x, y}, BWAPI::UnitTypes::Terran_Supply_Depot,
                                        builder, false)) continue;
                const int score = (x - wantedX) * (x - wantedX)
                    + (y - wantedY) * (y - wantedY);
                if (score < best) { best = score; selectedX = x; selectedY = y; }
            }
        return best < (1 << 30);
    }
    static std::string state(BWAPI::Unit unit) {
        return unit ? std::to_string(unit->getID()) + ":"
            + std::to_string(unit->isCompleted()) + ":"
            + std::to_string(unit->getRemainingBuildTime()) : "none";
    }
    void event(BWAPI::Game* game, const char* stage, const std::string& detail) const {
        auto owner = game->getPlayer(1);
        std::cerr << "[economy-e0] role=" << (controller_ ? "controller" : "publisher")
                  << " frame=" << game->getFrameCount() << " stage=" << stage
                  << " minerals=" << (owner ? owner->minerals() : -1)
                  << " gas=" << (owner ? owner->gas() : -1)
                  << " " << detail << std::endl;
    }
    void order(BWAPI::Game* game, const char* name, bool accepted) const {
        event(game, name, "accepted=" + std::to_string(accepted)
            + " error=" + game->getLastError().getName());
    }
    bool controller_ = false, initial_ = false;
    int stage_ = 0, deliveries_ = 0, pauseFrame_ = 0;
    int initialMinerals_ = 0, lastMinerals_ = 0, lastGas_ = 0;
    bool approachIssued_ = false;
    int approachFrame_ = 0;
    int destructionFrame_ = 0;
    int depotX_ = 135, depotY_ = 104, cancelX_ = 140, cancelY_ = 104;
};
