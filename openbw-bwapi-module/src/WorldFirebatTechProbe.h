#pragma once

#include <BWAPI.h>
#include <cstdlib>
#include <iostream>

// Test-only native experiment. The controller issues synchronized OpenBW
// actions; both participants independently report the resulting BWAPI state.
class WorldFirebatTechProbe {
public:
    explicit WorldFirebatTechProbe(bool controller) : controller_(controller) {}
    void onUnitCreate(BWAPI::Unit unit) {
        if (std::getenv("BRIDGE_TEST_FIREBAT_TECH") && unit
            && unit->getType() == BWAPI::UnitTypes::Terran_Firebat)
            std::cerr << "[firebat-tech] role=" << role() << " stage=unit_created id="
                      << unit->getID() << " completed=" << unit->isCompleted() << std::endl;
    }

    void onFrame(BWAPI::Game* game) {
        if (!std::getenv("BRIDGE_TEST_FIREBAT_TECH") || game->getFrameCount() < 120) return;
        BWAPI::Player terran = nullptr;
        for (auto player : game->getPlayers())
            if (player && player->getID() == 1 && player->getRace() == BWAPI::Races::Terran)
                terran = player;
        if (!terran) return;
        if (!resourcesSet_) {
            resourcesSet_ = true;
            const char* minerals = std::getenv("BRIDGE_TERRAN_STARTING_MINERALS");
            const char* gas = std::getenv("BRIDGE_TERRAN_STARTING_GAS");
            if (!minerals || !*minerals) terran->setMinerals(500);
            if (!gas || !*gas) terran->setGas(250);
        }
        BWAPI::Unit barracks = nullptr, academy = nullptr;
        int firebats = 0;
        for (auto unit : game->getAllUnits()) {
            if (!unit || !unit->exists() || unit->getPlayer() != terran) continue;
            if (unit->getType() == BWAPI::UnitTypes::Terran_Barracks) barracks = unit;
            if (unit->getType() == BWAPI::UnitTypes::Terran_Academy) academy = unit;
            if (unit->getType() == BWAPI::UnitTypes::Terran_Firebat && unit->isCompleted()) ++firebats;
        }
        if (controller_ && !barracks && !barracksIssued_) {
            barracksIssued_ = true;
            create(game, terran, BWAPI::UnitTypes::Terran_Barracks);
        }
        if (!barracks || !barracks->isCompleted()) return;
        if (!beforeReported_ && !academy) {
            beforeReported_ = true;
            bool requiresAcademy = false;
            for (const auto& requirement : BWAPI::UnitTypes::Terran_Firebat.requiredUnits())
                if (requirement.first == BWAPI::UnitTypes::Terran_Academy && requirement.second > 0)
                    requiresAcademy = true;
            std::cerr << "[firebat-tech] role=" << role() << " stage=before"
                      << " requires_academy=" << requiresAcademy
                      << " barracks_completed=" << barracks->isCompleted()
                      << " can_train=" << barracks->canTrain(BWAPI::UnitTypes::Terran_Firebat)
                      << " can_train_unchecked=" << barracks->canTrain(BWAPI::UnitTypes::Terran_Firebat, false, false)
                      << " minerals=" << terran->minerals() << " gas=" << terran->gas()
                      << " supply=" << terran->supplyUsed() << "/" << terran->supplyTotal()
                      << " queue=" << barracks->getTrainingQueue().size() << std::endl;
        }
        if (controller_ && beforeReported_ && !academy && !academyIssued_) {
            academyIssued_ = true;
            create(game, terran, BWAPI::UnitTypes::Terran_Academy);
        }
        if (academy && academy->isCompleted() && !afterReported_) {
            afterReported_ = true;
            std::cerr << "[firebat-tech] role=" << role() << " stage=academy"
                      << " academy_completed=" << academy->isCompleted()
                      << " academy_owner=" << academy->getPlayer()->getID()
                      << " can_train=" << barracks->canTrain(BWAPI::UnitTypes::Terran_Firebat)
                      << " can_train_unchecked=" << barracks->canTrain(BWAPI::UnitTypes::Terran_Firebat, false, false)
                      << " minerals=" << terran->minerals() << " gas=" << terran->gas()
                      << " supply=" << terran->supplyUsed() << "/" << terran->supplyTotal()
                      << " queue=" << barracks->getTrainingQueue().size() << std::endl;
        }
        if (controller_ && afterReported_ && !trainIssued_) {
            trainIssued_ = true;
            const int minerals = terran->minerals(), gas = terran->gas();
            const bool accepted = barracks->train(BWAPI::UnitTypes::Terran_Firebat);
            std::cerr << "[firebat-tech] role=controller stage=train accepted=" << accepted
                      << " minerals_before=" << minerals << " gas_before=" << gas
                      << " minerals_after=" << terran->minerals() << " gas_after=" << terran->gas()
                      << " queue=" << barracks->getTrainingQueue().size() << std::endl;
        }
        if (!controller_ && afterReported_ && !queueReported_
            && !barracks->getTrainingQueue().empty()) {
            queueReported_ = true;
            std::cerr << "[firebat-tech] role=publisher stage=queue minerals="
                      << terran->minerals() << " gas=" << terran->gas()
                      << " remaining=" << barracks->getRemainingTrainTime() << std::endl;
        }
        if (trainIssued_ && firebats > 0 && !completedReported_) {
            completedReported_ = true;
            std::cerr << "[firebat-tech] role=" << role() << " stage=completed firebats="
                      << firebats << " minerals=" << terran->minerals()
                      << " gas=" << terran->gas() << std::endl;
        }
        if (trainIssued_ && !completedReported_ && controller_
            && game->getFrameCount() % 120 == 0)
            std::cerr << "[firebat-tech] role=controller stage=progress frame="
                      << game->getFrameCount() << " queue=" << barracks->getTrainingQueue().size()
                      << " remaining=" << barracks->getRemainingTrainTime()
                      << " firebats=" << firebats << std::endl;
        if (controller_ && completedReported_ && academy && !removedIssued_) {
            removedIssued_ = true;
            game->killUnit(academy);
        }
        if (afterReported_ && completedReported_ && !academy && !removedReported_) {
            removedReported_ = true;
            std::cerr << "[firebat-tech] role=" << role() << " stage=removed can_train="
                      << barracks->canTrain(BWAPI::UnitTypes::Terran_Firebat)
                      << " firebats=" << firebats << " minerals=" << terran->minerals()
                      << " gas=" << terran->gas() << std::endl;
        }
    }

private:
    const char* role() const { return controller_ ? "controller" : "publisher"; }
    void create(BWAPI::Game* game, BWAPI::Player owner, BWAPI::UnitType type) {
        const int firstX = type == BWAPI::UnitTypes::Terran_Academy ? 150 : 96;
        for (int y = 100; y < 180; y += 3)
            for (int x = firstX; x < 190; x += 4)
                if (game->canBuildHere({x, y}, type, nullptr, true)) {
                    game->createUnit(owner, type, {x * 32 + type.tileWidth() * 16,
                                                   y * 32 + type.tileHeight() * 16});
                    std::cerr << "[firebat-tech] role=controller stage=create type=" << type.getName()
                              << " x=" << x << " y=" << y << std::endl;
                    return;
                }
        std::cerr << "[firebat-tech] role=controller stage=create_failed type="
                  << type.getName() << std::endl;
    }
    bool controller_ = false;
    bool resourcesSet_ = false, barracksIssued_ = false, academyIssued_ = false;
    bool beforeReported_ = false, afterReported_ = false, trainIssued_ = false;
    bool completedReported_ = false, removedIssued_ = false, removedReported_ = false;
    bool queueReported_ = false;
};
