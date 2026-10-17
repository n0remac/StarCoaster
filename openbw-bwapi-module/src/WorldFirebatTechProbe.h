#pragma once

#include <BWAPI.h>
#include <cstdlib>
#include <iostream>
#include <map>
#include <vector>

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
        if (std::getenv("BRIDGE_TEST_FIREBAT_ACADEMY_COUNT"))
            testAcademyCount(game, terran, barracks, firebats);
        else if (controller_ && completedReported_ && academy && !removedIssued_) {
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
        if (std::getenv("BRIDGE_TEST_FIREBAT_SPLASH"))
            testSplash(game, terran);
    }

private:
    const char* role() const { return controller_ ? "controller" : "publisher"; }
    void testAcademyCount(BWAPI::Game* game, BWAPI::Player terran,
                          BWAPI::Unit barracks, int firebats) {
        if (!firebats) return;
        std::vector<BWAPI::Unit> academies;
        for (auto unit : game->getAllUnits())
            if (unit && unit->exists() && unit->getPlayer() == terran
                && unit->getType() == BWAPI::UnitTypes::Terran_Academy
                && unit->isCompleted())
                academies.push_back(unit);
        int requiredAcademies = 0;
        for (const auto& requirement : BWAPI::UnitTypes::Terran_Firebat.requiredUnits())
            if (requirement.first == BWAPI::UnitTypes::Terran_Academy)
                requiredAcademies = requirement.second;
        const bool prerequisiteMet = requiredAcademies > 0
            && academies.size() >= static_cast<size_t>(requiredAcademies);
        if (controller_ && academies.size() == 1 && !secondAcademyIssued_) {
            secondAcademyIssued_ = true;
            create(game, terran, BWAPI::UnitTypes::Terran_Academy);
        }
        if (academies.size() == 2 && !twoAcademiesReported_) {
            twoAcademiesReported_ = true;
            twoAcademiesFrame_ = game->getFrameCount();
            std::cerr << "[firebat-count] role=" << role() << " academies=2 can_train="
                      << barracks->canTrain(BWAPI::UnitTypes::Terran_Firebat)
                      << " requirement_met=" << prerequisiteMet
                      << " minerals=" << terran->minerals() << " gas=" << terran->gas() << std::endl;
        }
        if (controller_ && academies.size() == 2 && twoAcademiesReported_
            && !firstAcademyRemoved_ && game->getFrameCount() - twoAcademiesFrame_ >= 10) {
            firstAcademyRemoved_ = true;
            game->killUnit(academies[0]);
        }
        if (firstAcademyRemoved_ && academies.size() == 1 && !oneAcademyReported_) {
            oneAcademyReported_ = true;
            oneAcademyFrame_ = game->getFrameCount();
            std::cerr << "[firebat-count] role=" << role() << " academies=1 can_train="
                      << barracks->canTrain(BWAPI::UnitTypes::Terran_Firebat)
                      << " requirement_met=" << prerequisiteMet
                      << " minerals=" << terran->minerals() << " gas=" << terran->gas() << std::endl;
        }
        if (!controller_ && twoAcademiesReported_ && academies.size() == 1
            && !oneAcademyReported_) {
            oneAcademyReported_ = true;
            std::cerr << "[firebat-count] role=publisher academies=1 can_train="
                      << barracks->canTrain(BWAPI::UnitTypes::Terran_Firebat)
                      << " requirement_met=" << prerequisiteMet
                      << " minerals=" << terran->minerals() << " gas=" << terran->gas() << std::endl;
        }
        if (controller_ && academies.size() == 1 && oneAcademyReported_
            && !secondAcademyRemoved_ && game->getFrameCount() - oneAcademyFrame_ >= 10) {
            secondAcademyRemoved_ = true;
            game->killUnit(academies[0]);
        }
        if (twoAcademiesReported_ && oneAcademyReported_ && academies.empty()
            && !zeroAcademiesReported_) {
            zeroAcademiesReported_ = true;
            std::cerr << "[firebat-count] role=" << role() << " academies=0 can_train="
                      << barracks->canTrain(BWAPI::UnitTypes::Terran_Firebat)
                      << " requirement_met=" << prerequisiteMet
                      << " minerals=" << terran->minerals() << " gas=" << terran->gas() << std::endl;
        }
    }
    void testSplash(BWAPI::Game* game, BWAPI::Player terran) {
        BWAPI::Unit firebat = nullptr;
        BWAPI::Player zerg = nullptr;
        for (auto player : game->getPlayers())
            if (player && player->getRace() == BWAPI::Races::Zerg) zerg = player;
        for (auto unit : game->getAllUnits())
            if (unit && unit->exists() && unit->getPlayer() == terran
                && unit->getType() == BWAPI::UnitTypes::Terran_Firebat && unit->isCompleted())
                firebat = unit;
        if (!firebat || !zerg) return;
        if (controller_ && !splashCreated_) {
            splashCreated_ = true;
            const auto at = firebat->getPosition();
            for (int offset : {48, 68}) {
                const auto unit = game->createUnit(zerg, BWAPI::UnitTypes::Zerg_Zergling,
                                                   {at.x + offset, at.y});
                std::cerr << "[firebat-splash] role=controller stage=create offset=" << offset
                          << " native=" << (unit ? unit->getID() : -1) << std::endl;
            }
        }
        std::vector<BWAPI::Unit> nearby;
        const auto at = firebat->getPosition();
        for (auto unit : game->getAllUnits())
            if (unit && unit->exists() && unit->getPlayer() == zerg
                && unit->getType() == BWAPI::UnitTypes::Zerg_Zergling
                && unit->getPosition().getDistance(at) < 140)
                nearby.push_back(unit);
        if (nearby.size() < 2) return;
        if (controller_ && !splashAttackIssued_) {
            splashAttackIssued_ = true;
            const bool accepted = firebat->attack(nearby[0]);
            std::cerr << "[firebat-splash] role=controller stage=attack accepted=" << accepted
                      << " target=" << nearby[0]->getID() << std::endl;
        }
        int damagedThisFrame = 0;
        for (auto unit : nearby) {
            const int id = unit->getID(), hp = unit->getHitPoints();
            const auto previous = splashHP_.find(id);
            if (previous != splashHP_.end() && hp < previous->second) ++damagedThisFrame;
            splashHP_[id] = hp;
        }
        if (!splashReported_ && damagedThisFrame >= 2) {
            splashReported_ = true;
            std::cerr << "[firebat-splash] role=" << role() << " stage=splash frame="
                      << game->getFrameCount() << " damaged=" << damagedThisFrame
                      << " hp=" << nearby[0]->getHitPoints() << ","
                      << nearby[1]->getHitPoints() << std::endl;
        }
    }
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
    bool splashCreated_ = false, splashAttackIssued_ = false, splashReported_ = false;
    std::map<int, int> splashHP_;
    bool secondAcademyIssued_ = false, twoAcademiesReported_ = false;
    bool firstAcademyRemoved_ = false, oneAcademyReported_ = false;
    bool secondAcademyRemoved_ = false, zeroAcademiesReported_ = false;
    int twoAcademiesFrame_ = 0, oneAcademyFrame_ = 0;
};
