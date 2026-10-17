#pragma once

#include <BWAPI.h>
#include <cstdlib>
#include <iostream>

// Test-only two-participant observation of the pinned Factory -> Armory -> Goliath rule.
class WorldGoliathProbe {
public:
    explicit WorldGoliathProbe(bool controller) : controller_(controller) {}

    void onFrame(BWAPI::Game* game) {
        if (!std::getenv("BRIDGE_TEST_GOLIATH_NATIVE") || game->getFrameCount() < 120) return;
        BWAPI::Player terran = nullptr, zerg = nullptr;
        for (auto player : game->getPlayers()) {
            if (player && player->getID() == 1 && player->getRace() == BWAPI::Races::Terran) terran = player;
            if (player && player->getRace() == BWAPI::Races::Zerg) zerg = player;
        }
        if (!terran) return;
        BWAPI::Unit factory = nullptr, armory = nullptr, goliath = nullptr, target = nullptr;
        for (auto unit : game->getAllUnits()) {
            if (!unit || !unit->exists()) continue;
            if (unit->getPlayer() == terran) {
                if (unit->getType() == BWAPI::UnitTypes::Terran_Factory) factory = unit;
                if (unit->getType() == BWAPI::UnitTypes::Terran_Armory) armory = unit;
                if (unit->getType() == BWAPI::UnitTypes::Terran_Goliath && unit->isCompleted()) goliath = unit;
            } else if (unit->getPlayer() == zerg && unit->getType() == BWAPI::UnitTypes::Zerg_Zergling)
                target = unit;
        }
        if (controller_ && !factory && !factoryIssued_) {
            factoryIssued_ = true;
            create(game, terran, BWAPI::UnitTypes::Terran_Factory);
        }
        if (!factory || !factory->isCompleted()) return;
        if (!beforeReported_ && !armory) {
            beforeReported_ = true;
            int requiredArmories = 0;
            for (const auto& requirement : BWAPI::UnitTypes::Terran_Goliath.requiredUnits())
                if (requirement.first == BWAPI::UnitTypes::Terran_Armory) requiredArmories = requirement.second;
            std::cerr << "[goliath-tech] role=" << role() << " stage=before required_armory="
                      << requiredArmories << " can_train=" << factory->canTrain(BWAPI::UnitTypes::Terran_Goliath)
                      << " minerals=" << terran->minerals() << " gas=" << terran->gas() << std::endl;
        }
        if (controller_ && beforeReported_ && !armory && !armoryIssued_) {
            armoryIssued_ = true;
            create(game, terran, BWAPI::UnitTypes::Terran_Armory);
        }
        if (!armory || !armory->isCompleted()) {
            if (completedReported_ && !removedReported_) {
                removedReported_ = true;
                std::cerr << "[goliath-tech] role=" << role() << " stage=removed can_train="
                          << factory->canTrain(BWAPI::UnitTypes::Terran_Goliath)
                          << " goliath_alive=" << (goliath && goliath->exists()) << std::endl;
            }
            return;
        }
        if (!afterReported_) {
            afterReported_ = true;
            std::cerr << "[goliath-tech] role=" << role() << " stage=after armory_hp="
                      << armory->getHitPoints() << " factory_hp=" << factory->getHitPoints()
                      << " can_train=" << factory->canTrain(BWAPI::UnitTypes::Terran_Goliath)
                      << std::endl;
        }
        if (controller_ && !trainingIssued_) {
            trainingIssued_ = true;
            const int minerals = terran->minerals(), gas = terran->gas(), supply = terran->supplyUsed();
            const bool accepted = factory->train(BWAPI::UnitTypes::Terran_Goliath);
            std::cerr << "[goliath-tech] role=controller stage=train accepted=" << accepted
                      << " minerals=" << minerals << "->" << terran->minerals()
                      << " gas=" << gas << "->" << terran->gas()
                      << " supply=" << supply << "->" << terran->supplyUsed() << std::endl;
        }
        if (goliath && !completedReported_) {
            completedReported_ = true;
            std::cerr << "[goliath-tech] role=" << role() << " stage=completed native="
                      << goliath->getID() << " hp=" << goliath->getHitPoints() << std::endl;
        }
        if (controller_ && goliath && !targetIssued_ && zerg) {
            targetIssued_ = true;
            auto enemy = game->createUnit(zerg, BWAPI::UnitTypes::Zerg_Zergling,
                                          {goliath->getPosition().x + 120, goliath->getPosition().y});
            std::cerr << "[goliath-tech] role=controller stage=target native="
                      << (enemy ? enemy->getID() : -1) << std::endl;
        }
        if (controller_ && target && goliath && !attackIssued_) {
            attackIssued_ = true;
            const bool accepted = goliath->attack(target);
            std::cerr << "[goliath-tech] role=controller stage=attack accepted=" << accepted
                      << " target_hp=" << target->getHitPoints() << std::endl;
        }
        if (controller_ && completedReported_ && attackIssued_ && !armoryRemoved_
            && game->getFrameCount() > 1200) {
            armoryRemoved_ = true;
            game->killUnit(armory);
        }
    }

private:
    const char* role() const { return controller_ ? "controller" : "publisher"; }
    void create(BWAPI::Game* game, BWAPI::Player owner, BWAPI::UnitType type) {
        for (int y = 100; y < 180; y += 2)
            for (int x = 100; x < 190; x += 2)
                if (game->canBuildHere({x, y}, type, nullptr, true)) {
                    auto unit = game->createUnit(owner, type,
                        {x * 32 + type.tileWidth() * 16, y * 32 + type.tileHeight() * 16});
                    std::cerr << "[goliath-tech] role=controller stage=create type=" << type.getName()
                              << " native=" << (unit ? unit->getID() : -1) << std::endl;
                    return;
                }
        std::cerr << "[goliath-tech] role=controller stage=create_failed type="
                  << type.getName() << std::endl;
    }
    bool controller_ = false;
    bool factoryIssued_ = false, beforeReported_ = false, armoryIssued_ = false;
    bool afterReported_ = false, trainingIssued_ = false, completedReported_ = false;
    bool targetIssued_ = false, attackIssued_ = false, armoryRemoved_ = false, removedReported_ = false;
};
