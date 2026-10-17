#pragma once

#include <BWAPI.h>
#include <cstdlib>
#include <iostream>
#include <sstream>

// Test-only two-participant probe. OpenBW executes the actions; each participant
// independently observes prerequisite, supply, production, and healing state.
class WorldMedicVultureProbe {
public:
    explicit WorldMedicVultureProbe(bool controller) : controller_(controller) {}

    void onFrame(BWAPI::Game* game) {
        if (!std::getenv("BRIDGE_TEST_MEDIC_VULTURE_NATIVE") || game->getFrameCount() < 120)
            return;
        BWAPI::Player owner = nullptr;
        for (auto player : game->getPlayers())
            if (player && player->getID() == 1 && player->getRace() == BWAPI::Races::Terran)
                owner = player;
        if (!owner) return;
        BWAPI::Unit barracks = nullptr, academy = nullptr, factory = nullptr;
        BWAPI::Unit depot = nullptr, medic = nullptr, vulture = nullptr, marine = nullptr;
        for (auto unit : game->getAllUnits()) {
            if (!unit || !unit->exists() || unit->getPlayer() != owner) continue;
            const auto type = unit->getType();
            if (type == BWAPI::UnitTypes::Terran_Barracks) barracks = unit;
            else if (type == BWAPI::UnitTypes::Terran_Academy) academy = unit;
            else if (type == BWAPI::UnitTypes::Terran_Factory) factory = unit;
            else if (type == BWAPI::UnitTypes::Terran_Supply_Depot && unit->getPosition().x > 500)
                depot = unit; // Exclude Mt. Zergling's existing supply fixture.
            else if (type == BWAPI::UnitTypes::Terran_Medic && unit->isCompleted()) medic = unit;
            else if (type == BWAPI::UnitTypes::Terran_Vulture && unit->isCompleted()) vulture = unit;
            else if (type == BWAPI::UnitTypes::Terran_Marine) marine = unit;
        }
        if (controller_ && !barracks && !barracksIssued_) {
            barracksIssued_ = true;
            create(game, owner, BWAPI::UnitTypes::Terran_Barracks);
        }
        if (!barracks || !barracks->isCompleted()) return;
        if (afterReported_ && !depot && !academy && !removedReported_
            && owner->supplyTotal() < supplyAfter_) {
            removedReported_ = true;
            std::cerr << "[next-tech] role=" << role() << " stage=removed supply="
                      << owner->supplyTotal() << " medic="
                      << barracks->canTrain(BWAPI::UnitTypes::Terran_Medic)
                      << " vulture=" << (factory && factory->canTrain(BWAPI::UnitTypes::Terran_Vulture))
                      << std::endl;
        }
        if (!beforeReported_ && !academy) {
            beforeReported_ = true;
            std::cerr << "[next-tech] role=" << role() << " stage=before"
                      << " medic=" << barracks->canTrain(BWAPI::UnitTypes::Terran_Medic)
                      << " supply=" << owner->supplyTotal()
                      << " minerals=" << owner->minerals() << " gas=" << owner->gas()
                      << std::endl;
        }
        if (controller_ && beforeReported_ && !academy && !academyIssued_) {
            academyIssued_ = true;
            create(game, owner, BWAPI::UnitTypes::Terran_Academy);
        }
        if (controller_ && academy && !factory && !factoryIssued_) {
            factoryIssued_ = true;
            create(game, owner, BWAPI::UnitTypes::Terran_Factory);
        }
        if (controller_ && factory && !depot && !depotIssued_) {
            depotIssued_ = true;
            create(game, owner, BWAPI::UnitTypes::Terran_Supply_Depot);
        }
        if (!academy || !factory || !depot || !academy->isCompleted()
            || !factory->isCompleted() || !depot->isCompleted()) return;
        if (!afterReported_) {
            afterReported_ = true;
            supplyAfter_ = owner->supplyTotal();
            std::ostringstream line;
            line << "[next-tech] role=" << role() << " stage=after"
                 << " medic=" << barracks->canTrain(BWAPI::UnitTypes::Terran_Medic)
                 << " academy=" << academy->isCompleted()
                 << " vulture=" << factory->canTrain(BWAPI::UnitTypes::Terran_Vulture)
                 << " supply=" << owner->supplyTotal()
                 << " depot_hp=" << depot->getHitPoints()
                 << " factory_hp=" << factory->getHitPoints() << '\n';
            std::cerr << line.str();
        }
        if (controller_ && !trainingIssued_) {
            trainingIssued_ = true;
            const int minerals = owner->minerals(), gas = owner->gas();
            const bool medicAccepted = barracks->train(BWAPI::UnitTypes::Terran_Medic);
            const bool vultureAccepted = factory->train(BWAPI::UnitTypes::Terran_Vulture);
            std::cerr << "[next-tech] role=controller stage=train medic=" << medicAccepted
                      << " vulture=" << vultureAccepted << " minerals=" << minerals
                      << "->" << owner->minerals() << " gas=" << gas << "->"
                      << owner->gas() << std::endl;
        }
        if (medic && vulture && !completedReported_) {
            completedReported_ = true;
            std::cerr << "[next-tech] role=" << role() << " stage=completed medic="
                      << medic->getID() << " vulture=" << vulture->getID()
                      << " minerals=" << owner->minerals() << " gas=" << owner->gas()
                      << std::endl;
        }
        if (controller_ && medic && !marine && !marineIssued_) {
            marineIssued_ = true;
            game->createUnit(owner, BWAPI::UnitTypes::Terran_Marine,
                             {medic->getPosition().x + 96, medic->getPosition().y});
        }
        if (controller_ && marine && marine->isCompleted() && !damageIssued_) {
            damageIssued_ = true;
            marine->setHitPoints(20);
        }
        if (marine && medic && marine->getHitPoints() <= 20 && !damageReported_) {
            damageReported_ = true;
            std::cerr << "[next-tech] role=" << role() << " stage=damaged marine_hp="
                      << marine->getHitPoints() << " energy=" << medic->getEnergy() << std::endl;
        }
        if (controller_ && damageReported_ && marine && medic && !healIssued_) {
            healIssued_ = true;
            const bool accepted = medic->useTech(BWAPI::TechTypes::Healing, marine);
            std::cerr << "[next-tech] role=controller stage=heal_order accepted=" << accepted
                      << " marine_hp=" << marine->getHitPoints()
                      << " energy=" << medic->getEnergy() << std::endl;
        }
        if (damageReported_ && marine && medic && marine->getHitPoints() > 20 && !healedReported_) {
            healedReported_ = true;
            std::cerr << "[next-tech] role=" << role() << " stage=healed frame="
                      << game->getFrameCount() << " marine_hp=" << marine->getHitPoints()
                      << " energy=" << medic->getEnergy()
                      << " order=" << medic->getOrder().getName() << std::endl;
        }
        if (controller_ && healedReported_ && !depotRemoved_) {
            depotRemoved_ = true;
            game->killUnit(depot);
            game->killUnit(academy);
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
                    std::cerr << "[next-tech] role=controller stage=create type=" << type.getName()
                              << " native=" << (unit ? unit->getID() : -1) << std::endl;
                    return;
                }
        std::cerr << "[next-tech] role=controller stage=create_failed type="
                  << type.getName() << std::endl;
    }
    bool controller_ = false;
    bool barracksIssued_ = false, beforeReported_ = false;
    bool academyIssued_ = false, factoryIssued_ = false, depotIssued_ = false;
    bool afterReported_ = false, trainingIssued_ = false, completedReported_ = false;
    bool marineIssued_ = false, damageIssued_ = false, damageReported_ = false;
    bool healIssued_ = false, healedReported_ = false;
    bool depotRemoved_ = false, removedReported_ = false;
    int supplyAfter_ = 0;
};
