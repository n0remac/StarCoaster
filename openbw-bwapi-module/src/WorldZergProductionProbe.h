#pragma once

#include <BWAPI.h>
#include <cstdlib>
#include <iostream>
#include <set>
#include <vector>

// Test-only observation of the native Hatchery -> Larva -> Egg -> two Zerglings path.
class WorldZergProductionProbe {
public:
    explicit WorldZergProductionProbe(bool zergParticipant) : zergParticipant_(zergParticipant) {}

    void onFrame(BWAPI::Game* game) {
        if (!std::getenv("BRIDGE_TEST_ZERG_PRODUCTION") || game->getFrameCount() < 120) return;
        const char* removePool = std::getenv("BRIDGE_TEST_ZERG_PRODUCTION_REMOVE_POOL");
        if (removePool && *removePool && !removedPool_) {
            std::vector<BWAPI::Unit> pools;
            for (auto unit : game->getAllUnits())
                if (unit && unit->exists() && unit->getPlayer()
                    && unit->getPlayer()->getID() == 0
                    && unit->getType() == BWAPI::UnitTypes::Zerg_Spawning_Pool)
                    pools.push_back(unit);
            if (pools.empty()) return;
            for (auto pool : pools) game->removeUnit(pool);
            removedPool_ = true;
            std::cerr << "[zerg-production] role=" << role()
                      << " stage=pool_removed count=" << pools.size() << std::endl;
            return;
        }
        if (removePool && *removePool && game->getPlayer(0)
            && game->getPlayer(0)->completedUnitCount(BWAPI::UnitTypes::Zerg_Spawning_Pool) > 0)
            return;
        const char* fillSupply = std::getenv("BRIDGE_TEST_ZERG_PRODUCTION_FILL_SUPPLY");
        if (fillSupply && *fillSupply && !filledSupply_) {
            auto owner = game->getPlayer(0);
            if (!owner) return;
            for (int index = 0; index < 4; ++index)
                game->createUnit(owner, BWAPI::UnitTypes::Zerg_Drone,
                    {256 + (index % 3) * 32, 256 + (index / 3) * 32});
            game->createUnit(owner, BWAPI::UnitTypes::Zerg_Zergling, {352, 288});
            filledSupply_ = true;
            std::cerr << "[zerg-production] role=" << role() << " stage=supply_filled units=5 used="
                      << owner->supplyUsed() << " total=" << owner->supplyTotal() << std::endl;
            return;
        }
        BWAPI::Unit hatchery = nullptr;
        std::set<int> eggs, zerglings;
        for (auto unit : game->getAllUnits()) {
            if (!unit || !unit->exists() || !unit->getPlayer() || unit->getPlayer()->getID() != 0) continue;
            if (unit->getType() == BWAPI::UnitTypes::Zerg_Hatchery) hatchery = unit;
            if (unit->getType() == BWAPI::UnitTypes::Zerg_Egg) eggs.insert(unit->getID());
            if (unit->getType() == BWAPI::UnitTypes::Zerg_Zergling && unit->isCompleted())
                zerglings.insert(unit->getID());
        }
        if (!hatchery || !hatchery->isCompleted()) return;
        const auto larvae = hatchery->getLarva();
        if (!reportedLarvae_ && !larvae.empty()) {
            reportedLarvae_ = true;
            std::cerr << "[zerg-production] role=" << role() << " stage=larva hatchery="
                      << hatchery->getID() << " owner=" << hatchery->getPlayer()->getID()
                      << " completed=" << hatchery->isCompleted() << " count=" << larvae.size()
                      << " native=" << (*larvae.begin())->getID() << std::endl;
        }
        if (zergParticipant_ && reportedLarvae_ && !issued_) {
            issued_ = true;
            issueFrame_ = game->getFrameCount();
            auto owner = hatchery->getPlayer();
            const int minerals = owner->minerals(), supply = owner->supplyUsed();
            const bool possible = hatchery->canTrain(BWAPI::UnitTypes::Zerg_Zergling);
            const bool accepted = hatchery->train(BWAPI::UnitTypes::Zerg_Zergling);
            std::cerr << "[zerg-production] role=publisher stage=train can_train=" << possible
                      << " accepted=" << accepted << " minerals=" << minerals << "->"
                      << owner->minerals() << " supply=" << supply << "->"
                      << owner->supplyUsed() << " supply_total=" << owner->supplyTotal()
                      << " pool_count=" << owner->completedUnitCount(BWAPI::UnitTypes::Zerg_Spawning_Pool)
                      << " larva=" << (*larvae.begin())->getID() << std::endl;
        }
        if (zergParticipant_ && issued_ && !reportedRejection_
            && std::getenv("BRIDGE_TEST_ZERG_PRODUCTION_REJECTION")
            && game->getFrameCount() >= issueFrame_ + 90) {
            reportedRejection_ = true;
            std::cerr << "[zerg-production] role=publisher stage=rejected egg_count="
                      << eggs.size() << " larva_count=" << larvae.size() << std::endl;
        }
        if (!reportedEgg_ && !eggs.empty()) {
            reportedEgg_ = true;
            std::cerr << "[zerg-production] role=" << role() << " stage=egg native="
                      << *eggs.begin() << " completed=0 remaining="
                      << game->getUnit(*eggs.begin())->getRemainingBuildTime()
                      << " larvae=" << larvae.size() << std::endl;
        }
        if (reportedEgg_ && !reportedHatch_ && zerglings.size() >= 2) {
            reportedHatch_ = true;
            auto it = zerglings.begin(); const int first = *it++; const int second = *it;
            std::cerr << "[zerg-production] role=" << role() << " stage=hatched first="
                      << first << " second=" << second << " egg_gone=" << eggs.empty()
                      << " minerals=" << hatchery->getPlayer()->minerals() << std::endl;
        }
    }
private:
    const char* role() const { return zergParticipant_ ? "publisher" : "controller"; }
    bool zergParticipant_ = false, issued_ = false, reportedLarvae_ = false;
    bool reportedEgg_ = false, reportedHatch_ = false, reportedRejection_ = false;
    bool removedPool_ = false;
    bool filledSupply_ = false;
    int issueFrame_ = 0;
};
