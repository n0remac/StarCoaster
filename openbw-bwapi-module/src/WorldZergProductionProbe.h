#pragma once

#include <BWAPI.h>
#include <cstdlib>
#include <iostream>
#include <set>

// Test-only observation of the native Hatchery -> Larva -> Egg -> two Zerglings path.
class WorldZergProductionProbe {
public:
    explicit WorldZergProductionProbe(bool zergParticipant) : zergParticipant_(zergParticipant) {}

    void onFrame(BWAPI::Game* game) {
        if (!std::getenv("BRIDGE_TEST_ZERG_PRODUCTION") || game->getFrameCount() < 120) return;
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
            auto owner = hatchery->getPlayer();
            const int minerals = owner->minerals(), supply = owner->supplyUsed();
            const bool possible = hatchery->canTrain(BWAPI::UnitTypes::Zerg_Zergling);
            const bool accepted = possible && hatchery->train(BWAPI::UnitTypes::Zerg_Zergling);
            std::cerr << "[zerg-production] role=publisher stage=train can_train=" << possible
                      << " accepted=" << accepted << " minerals=" << minerals << "->"
                      << owner->minerals() << " supply=" << supply << "->"
                      << owner->supplyUsed() << " supply_total=" << owner->supplyTotal()
                      << " larva=" << (*larvae.begin())->getID() << std::endl;
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
    bool reportedEgg_ = false, reportedHatch_ = false;
};
