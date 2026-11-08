#pragma once

#include <BWAPI.h>
#include "WorldStarcraftTypes.h"
#include <algorithm>
#include <climits>
#include <cstdint>
#include <cstdlib>
#include <iostream>
#include <map>
#include <string>
#include <utility>
#include <vector>

// Scenario policy. Native BWAPI orders, movement, target acquisition, and
// combat remain authoritative; the generic world adapter owns no target IDs.
class WorldAssaultController {
public:
    void configure(std::string objectiveID, std::string session = "", bool parkDefense = false,
                   bool baseProduction = false) {
        if (session == session_ && objectiveID == objectiveID_ && parkDefense == parkDefense_
            && baseProduction == baseProduction_) return;
        session_ = std::move(session);
        objectiveID_ = std::move(objectiveID);
        parkDefense_ = parkDefense;
        baseProduction_ = baseProduction;
        destinations_.clear();
        fallbackRallies_.clear();
        rallyIssueState_.clear();
        navigationEpoch_ = 1;
        started_ = false;
        notBeforeFrame_ = 0;
    }
    bool start(int frame, int delayFrames) {
        if (objectiveID_.empty() && !parkDefense_) return false;
        if (started_) return true;
        started_ = true;
        notBeforeFrame_ = frame + std::max(0, std::min(600, delayFrames));
        return true;
    }
    bool active(int frame) const {
        return (!objectiveID_.empty() || parkDefense_) && started_ && frame >= notBeforeFrame_;
    }
    const std::string& objectiveID() const { return objectiveID_; }
    bool parkDefense() const { return parkDefense_; }
    bool baseProduction() const { return baseProduction_; }

    void setWaveDestination(int nativeID, BWAPI::Position destination) {
        if (nativeID >= 0 && destination.isValid()) {
            destinations_[nativeID] = destination;
            rallyIssueState_.erase(nativeID);
        }
    }
    void forgetUnit(int nativeID) {
        destinations_.erase(nativeID);
        fallbackRallies_.erase(nativeID);
        rallyIssueState_.erase(nativeID);
    }
    void navigationChanged() {
        fallbackRallies_.clear();
        ++navigationEpoch_;
    }
    bool shouldIssueWaveRally(int nativeID, BWAPI::Position from, BWAPI::Position orderTarget,
                              bool idle, bool reachable) {
        const auto found = destinations_.find(nativeID);
        if (found == destinations_.end()) return false;
        if (baseProduction_ && !idle) return false;
        auto& state = rallyIssueState_[nativeID];
        if (!reachable) {
            state.blocked = true;
            return false;
        }
        if (state.blocked) {
            state.attempts = 0;
            state.blocked = false;
        }
        const auto goal = found->second;
        if (std::abs(goal.x-from.x)+std::abs(goal.y-from.y) < 64) return false;
        if (state.attempts == 0 || (state.attempts == 1 && idle && orderTarget != goal)) {
            ++state.attempts;
            return true;
        }
        return false;
    }
    BWAPI::Position rallyFor(int nativeID, int width, int height, BWAPI::Position from) {
        if (auto it = destinations_.find(nativeID); it != destinations_.end()) return it->second;
        if (auto it = fallbackRallies_.find(nativeID); it != fallbackRallies_.end()) return it->second;
        const auto points = interiorRallies(width, height, from);
        const auto rally = points.empty() ? from : points.front();
        fallbackRallies_[nativeID] = rally;
        return rally;
    }

    static std::vector<BWAPI::Position> interiorRallies(int width, int height, BWAPI::Position from) {
        std::vector<BWAPI::Position> points;
        for (int y = 1; y <= 3; ++y) for (int x = 1; x <= 3; ++x)
            points.emplace_back(width * 32 * x / 4, height * 32 * y / 4);
        std::sort(points.begin(), points.end(), [from](const auto& a, const auto& b) {
            const int da = std::abs(a.x - from.x) + std::abs(a.y - from.y);
            const int db = std::abs(b.x - from.x) + std::abs(b.y - from.y);
            return da < db;
        });
        return points;
    }

    void step(BWAPI::Game* game, BWAPI::Unit objective,
              const std::vector<BWAPI::Unit>& alternatives) {
        if (!game || !game->self()) return;
        for (auto unit : game->getAllUnits()) {
            if (!unit || !unit->exists() || unit->getPlayer() != game->self()) continue;
            const auto* kind = worldUnitType(unit->getType());
            if (!kind || std::string(kind->race) != "zerg" || std::string(kind->ownership) != "enemy"
                || !kind->spawnable || !unit->getType().canAttack()) continue;
            if (auto assigned = destinations_.find(unit->getID()); assigned != destinations_.end()) {
                auto& state = rallyIssueState_[unit->getID()];
                if (unit->isIdle() && state.checkedEpoch != navigationEpoch_) {
                    state.routeReachable = game->hasUnitTypePath(
                        unit->getType(), unit->getPosition(), assigned->second);
                    state.checkedEpoch = navigationEpoch_;
                }
                if (shouldIssueWaveRally(unit->getID(), unit->getPosition(),
                        unit->getOrderTargetPosition(), unit->isIdle(),
                        !unit->isIdle() || (unit->hasPath(assigned->second) && state.routeReachable))) {
                    if (unit->attack(assigned->second))
                        std::cerr << "[world] wave-rally native=" << unit->getID()
                                  << " x=" << assigned->second.x << " y=" << assigned->second.y
                                  << " frame=" << game->getFrameCount() << std::endl;
                    else rallyIssueState_.erase(unit->getID());
                }
                continue; // Native attack-move acquires and fights nearby targets.
            }
            if (baseProduction_) continue; // unassigned colony units remain at the Hatchery
            BWAPI::Unit target = !parkDefense_ && objective && objective->exists() ? objective : nullptr;
            if (!target) {
                int best = INT_MAX;
                for (auto candidate : alternatives) {
                    if (!candidate || !candidate->exists() || candidate->getPlayer() == game->self()) continue;
                    if (parkDefense_ && !unit->hasPath(candidate->getPosition())) continue;
                    const auto a = unit->getPosition(), b = candidate->getPosition();
                    const int distance = std::abs(a.x - b.x) + std::abs(a.y - b.y);
                    const int priority = parkDefense_ && candidate->getPlayer()
                        && candidate->getPlayer()->getID() == 1
                        ? (candidate->getType().isBuilding() ? 1 : 0) : 2;
                    const int score = priority * 100000 + distance;
                    if (score < best) { best = score; target = candidate; }
                }
            }
            if (target && unit->getOrderTarget() != target && unit->getTarget() != target)
                unit->attack(target);
            if (!target && parkDefense_) {
                const auto rally = rallyFor(unit->getID(), game->mapWidth(), game->mapHeight(), unit->getPosition());
                if (std::abs(rally.x - unit->getPosition().x) + std::abs(rally.y - unit->getPosition().y) >= 64
                    && unit->hasPath(rally) && unit->getOrderTargetPosition() != rally)
                    unit->attack(rally);
            }
        }
    }
private:
    std::string objectiveID_;
    std::string session_;
    bool parkDefense_ = false;
    bool baseProduction_ = false;
    int notBeforeFrame_ = 0;
    bool started_ = false;
    std::map<int, BWAPI::Position> destinations_;
    std::map<int, BWAPI::Position> fallbackRallies_;
    struct RallyIssueState {
        int attempts = 0;
        uint64_t checkedEpoch = 0;
        bool routeReachable = true;
        bool blocked = false;
    };
    std::map<int, RallyIssueState> rallyIssueState_;
    uint64_t navigationEpoch_ = 1;
};
