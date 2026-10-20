#pragma once

#include <BWAPI.h>
#include <nlohmann/json.hpp>
#include "WorldState.h"
#include "WorldNavigation.h"
#include "WorldActorRegistry.h"
#include "WorldAssaultController.h"
#include "WorldSpawnPlacement.h"
#include "WorldProductionFixture.h"
#include "WorldFirebatTechProbe.h"
#include "WorldMedicVultureProbe.h"
#include "WorldGoliathProbe.h"
#include "WorldZergProductionProbe.h"
#include "WorldBuildingState.h"
#include "BridgePerformance.h"

#include <arpa/inet.h>
#include <fcntl.h>
#include <sys/socket.h>
#include <unistd.h>

#include <algorithm>
#include <chrono>
#include <climits>
#include <cmath>
#include <cerrno>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <map>
#include <set>
#include <string>
#include <vector>

// All network input is parsed and applied by onFrame on the BWAPI simulation
// thread. The socket callback never touches game state.
class WorldAdapter {
    using json = nlohmann::json;
    struct Target { std::string id; BWAPI::Unit unit = nullptr; int proxyID = -1; int lastHP = 0;
        bool reported = false; std::string lifecycle = "active"; int x = 0, y = 0;
        int desiredHP = 0, healthFrame = 0; };
    struct PendingTarget { std::string id; int x = 0; int y = 0; int health = 0;
        std::string buildingType; int ownerID = -1;
        bool requested = false; int requestedFrame = 0; std::set<int> beforeIDs; };
    struct ScheduledRemoval { json message; std::string id; int frame = 0; };
    struct NativeSpawn {
        std::string requestID, unitType, state, actorID, reason;
        int index = 0, x = 0, y = 0, ownerID = -1, issueFrame = 0, candidateID = -1;
        int actualX = 0, actualY = 0;
        bool reported = false, fixture = false;
    };
public:
    ~WorldAdapter() { if (socket_ >= 0) ::close(socket_); }
    void onUnitCreate(BWAPI::Unit unit, int frame) {
        firebatTechProbe_.onUnitCreate(unit);
        if (std::getenv("BRIDGE_TEST_FIREBAT_GAMEPLAY") && unit
            && unit->getType() == BWAPI::UnitTypes::Terran_Firebat)
            std::cerr << "[firebat-gameplay] role=publisher created native=" << unit->getID()
                      << " frame=" << frame << " completed=" << unit->isCompleted() << std::endl;
        if (!unit || !unit->exists() || actorRegistry_.known(unit) || frame < 2) return;
        const auto type = unit->getType();
        if (!worldUnitType(type)) return;
        const auto position = unit->getPosition();
        pendingCreations_[unit->getID()] = {unit, frame, position.x, position.y};
    }
    void onUnitDestroy(BWAPI::Unit unit, int frame) {
        if (!unit) return;
        if (std::getenv("BRIDGE_TEST_FIREBAT_GAMEPLAY")
            && unit->getType() == BWAPI::UnitTypes::Terran_Firebat)
            std::cerr << "[firebat-gameplay] role=publisher destroyed native=" << unit->getID()
                      << " frame=" << frame << " hp=" << unit->getHitPoints()
                      << " last_snapshot_frame=" << (lastActors_.count(unit->getID())
                          ? lastActors_.at(unit->getID()).second : -1) << std::endl;
        if (!activeSpawn_.empty()) {
            auto& spawn = nativeSpawns_.at(activeSpawn_);
            if (spawn.candidateID == unit->getID() && spawn.state == "issued") {
                spawn.state = "failed"; spawn.reason = "native_died_before_registration";
                spawn.reported = false; activeSpawn_.clear();
            }
        }
        pendingCreations_.erase(unit->getID());
        publishedActors_.erase(unit->getID());
        publishedActorStates_.erase(unit->getID());
        if (auto last = lastActors_.find(unit->getID()); last != lastActors_.end())
            if (const auto* type = worldUnitType(unit->getType()))
                last->second.first["kind"] = type->id;
        const auto id = actorRegistry_.id(unit);
        for (auto& [key, spawn] : nativeSpawns_) {
            if (spawn.actorID != id || spawn.state != "created") continue;
            // A bridge can restart between native creation and the controller
            // binding. Replay the death as a terminal result for that request.
            spawn.state = "failed";
            spawn.reason = "native_died_before_ready";
            spawn.reported = false;
        }
        for (const auto& [canonical, actor] : actorRegistry_.runtime()) {
            if (id != "openbw:" + std::to_string(canonical)) continue;
            if (socket_ >= 0 && !session_.empty())
                send("actor.despawn", {{"id", id}, {"session", session_},
                    {"generation", actor.generation}}, revision_, frame);
            std::cerr << "[world] actor-despawn id=" << id << " frame=" << frame << std::endl;
            break;
        }
        actorRegistry_.forget(unit);
    }
    void onFrame(BWAPI::Game* game) {
        if (!startingResourcesApplied_)
            startingResourcesApplied_ = applyWorldProductionFixture(game);
        replenishWorldTerranResources(game);
        firebatTechProbe_.onFrame(game);
        medicVultureProbe_.onFrame(game);
        goliathProbe_.onFrame(game);
        zergProductionProbe_.onFrame(game);
        std::set<int> pendingIDs;
        for (const auto& [id, creation] : pendingCreations_) pendingIDs.insert(id);
        actorRegistry_.prepare(game, pendingIDs);
        resolveSpawnCandidates();
        registerPendingCreations();
        if (socket_ < 0) connect(game);
        if (socket_ < 0) return;
        char data[8192];
        // A dense park can stream thousands of snapshot chunks. Bound each
        // frame's read so TCP backpressure follows native parsing progress.
        // The old drain-to-EAGAIN loop accumulated the entire burst before
        // parsing and disconnected at 8 MiB despite valid 1 MiB lines.
        constexpr size_t maxBuffered = (1 << 20) + 8192;
        while (incoming_.size() < maxBuffered) {
            const ssize_t n = ::recv(socket_, data, sizeof(data), 0);
            if (n > 0) incoming_.append(data, static_cast<size_t>(n));
            else if (n == 0) { disconnect(); return; }
            else if (errno == EAGAIN || errno == EWOULDBLOCK) break;
            else { disconnect(); return; }
        }
        size_t newline;
        int processed = 0;
        while (processed++ < 64 && (newline = incoming_.find('\n')) != std::string::npos) {
            const auto line = incoming_.substr(0,newline); incoming_.erase(0,newline+1);
            if (line.size() > 1048576) { disconnect(); return; }
            try { handle(game,json::parse(line)); } catch (const std::exception& e) { std::cerr << "[world] invalid message: " << e.what() << std::endl; }
        }
        if (incoming_.size() >= maxBuffered && incoming_.find('\n') == std::string::npos) {
            std::cerr << "[world] snapshot line exceeds 1 MiB" << std::endl;
            disconnect(); return;
        }
        flush();
        applyScheduledNavigation(game);
        if (initializing_ || liveTargetsResolving_) resolveTargets(game);
        const int frame = game->getFrameCount();
        std::vector<std::string> failedHealthTargets;
        for (auto& [id, target] : targets_) {
            if (target.lifecycle != "pending_health") continue;
            const int hp = target.unit && target.unit->exists() ? target.unit->getHitPoints() : 0;
            if (hp == target.desiredHP) {
                target.lifecycle = "active";
                target.lastHP = hp;
                send("entity.state", {{"id", id},
                    {"proxy_id", "openbw:" + std::to_string(target.proxyID)},
                    {"proxy_x", target.x}, {"proxy_y", target.y}, {"health", hp}}, revision_, frame);
            } else if (frame - target.healthFrame >= 12) {
                reportUnsupported(id, "proxy_health_update_failed");
                failedHealthTargets.push_back(id);
            }
        }
        for (const auto& id : failedHealthTargets)
            retireTarget(game, id, "proxy_health_update_failed");
        if (!ready_) return;
        publishRuntimeEvents(frame);
        publishSpawnOutcomes(frame);
        if (!session_.empty() && frame % 24 == 0 && game->self()) {
            send("player.resources", {{"owner", game->self()->getID()},
                {"minerals", game->self()->minerals()}, {"gas", game->self()->gas()},
                {"supply_used", game->self()->supplyUsed()},
                {"supply_total", game->self()->supplyTotal()}}, revision_, frame);
            for (const auto& [id, target] : targets_) {
                auto unit = target.unit;
                if (!unit || !unit->exists() || unit->getPlayer() != game->self()) continue;
                const auto* building = worldBuildingType(unit->getType());
                if (!building) continue;
                send("building.state", worldBuildingState(game, unit, *building, id,
                    "openbw:" + std::to_string(target.proxyID)), revision_, frame);
            }
        }
        const char* spawnAt = std::getenv("BRIDGE_TEST_SPAWN_MARINE_FRAME");
        if (!testMarineSpawnRequested_ && spawnAt && *spawnAt) {
            char* end = nullptr;
            const long requested = std::strtol(spawnAt, &end, 10);
            if (end && !*end && requested > 0 && frame >= requested) {
                testMarineSpawnRequested_ = true;
                const int x = (18 + (game->mapWidth() - 64) / 2) * 32 + 16;
                const int y = (30 + (game->mapHeight() - 64) / 2) * 32 + 16;
                bool requested = false;
                for (int radius = 0; radius <= 4 && !requested; ++radius)
                    for (int dy = -radius; dy <= radius && !requested; ++dy)
                        for (int dx = -radius; dx <= radius && !requested; ++dx) {
                            if (std::max(std::abs(dx), std::abs(dy)) != radius) continue;
                            const int px = x + dx * 32, py = y + dy * 32;
                            requested = executeNativeSpawn(game, {{"request_id","fixture:marine"},
                                {"index",0}, {"unit_type","terran_marine"}, {"x",px}, {"y",py}}, true);
                            if (requested) std::cerr << "[world] requested native test Marine frame=" << frame
                                << " x=" << px << " y=" << py << std::endl;
                        }
                if (!requested) std::cerr << "[world] native test Marine fixture unavailable reason="
                    << spawnError_ << std::endl;
            }
        }
        const char* killAt = std::getenv("BRIDGE_TEST_KILL_MARINE_FRAME");
        if (testMarineCanonical_ && !testMarineKillRequested_ && killAt && *killAt) {
            char* end = nullptr;
            const long requested = std::strtol(killAt, &end, 10);
            if (end && !*end && requested > 0 && frame >= requested) {
                testMarineKillRequested_ = true;
                auto unit = actorRegistry_.lookup("openbw:" + std::to_string(testMarineCanonical_));
                if (unit && unit->exists()) {
                    game->killUnit(unit);
                    std::cerr << "[world] requested native test Marine death id=openbw:"
                              << testMarineCanonical_ << " frame=" << frame << std::endl;
                }
            }
        }
        const char* runtimeKillAt = std::getenv("BRIDGE_TEST_KILL_RUNTIME_MARINE_FRAME");
        if (!testRuntimeKillRequested_ && runtimeKillAt && *runtimeKillAt) {
            char* end = nullptr;
            const long requested = std::strtol(runtimeKillAt, &end, 10);
            if (end && !*end && requested > 0 && frame >= requested) {
                auto unit = actorRegistry_.lookup("openbw:3001");
                if (unit && unit->exists() && unit->getType() == BWAPI::UnitTypes::Terran_Marine) {
                    testRuntimeKillRequested_ = true;
                    game->killUnit(unit);
                    std::cerr << "[world] requested native runtime Marine death id=openbw:3001"
                              << " frame=" << frame << std::endl;
                }
            }
        }
        const char* firebatKillAfterAttack = std::getenv("BRIDGE_TEST_KILL_FIREBAT_AFTER_ATTACK");
        if (!testFirebatKillRequested_ && firebatKillAfterAttack && *firebatKillAfterAttack) {
            char* end = nullptr;
            const long requestedAttacks = std::strtol(firebatKillAfterAttack, &end, 10);
            auto unit = actorRegistry_.lookup("openbw:3001");
            const bool attackReady = unit && requestedAttacks > 0 && end && !*end
                && attackFrames_[unit->getID()] >= requestedAttacks;
            if (attackReady) {
                if (unit && unit->exists() && unit->getType() == BWAPI::UnitTypes::Terran_Firebat) {
                    testFirebatKillRequested_ = true;
                    const int attacks = attackFrames_[unit->getID()];
                    game->killUnit(unit);
                    std::cerr << "[world] requested native test Firebat death id=openbw:3001"
                              << " frame=" << frame << " attack_frames=" << attacks << std::endl;
                }
            }
        }
        for (auto& [id,target] : targets_) {
            const auto type = target.unit && target.unit->exists() ? target.unit->getType()
                : BWAPI::UnitTypes::None;
            const char* testHealth = nullptr;
            if (const char* requested = std::getenv("BRIDGE_TEST_BUILDING_HP")) {
                if (const auto* building = worldBuildingType(type)) {
                    const std::string prefix = std::string(building->id) + "=";
                    if (std::strncmp(requested, prefix.c_str(), prefix.size()) == 0)
                        testHealth = requested + prefix.size();
                }
            }
            // Keep the original focused test fixtures working during migration.
            if (!testHealth) testHealth = type == BWAPI::UnitTypes::Terran_Barracks
                ? std::getenv("BRIDGE_TEST_BARRACKS_HP")
                : type == BWAPI::UnitTypes::Terran_Academy
                    ? std::getenv("BRIDGE_TEST_ACADEMY_HP") : nullptr;
            if (!testBuildingDamageApplied_.count(id) && testHealth && *testHealth) {
                char* end = nullptr;
                const long requested = std::strtol(testHealth, &end, 10);
                if (end && !*end && requested > 0 && requested < type.maxHitPoints()) {
                    testBuildingDamageApplied_.insert(id);
                    target.unit->setHitPoints(static_cast<int>(requested));
                    std::cerr << "[world] test building HP requested id=" << id
                              << " hp=" << requested << " frame=" << frame << std::endl;
                }
            }
            const int hp = target.unit && target.unit->exists() ? target.unit->getHitPoints() : 0;
            if (target.lifecycle == "pending_health") continue;
            if (hp != target.lastHP) { target.lastHP=hp; send("entity.state",{{"id",id},{"proxy_id","openbw:"+std::to_string(target.proxyID)},
                {"proxy_x",target.x},{"proxy_y",target.y},{"health",hp}},revision_,frame); }
            if (hp==0 && !target.reported && (target.lifecycle=="active"
                || target.lifecycle=="destroyed_in_openbw")) {
                target.reported=true;
                target.lifecycle="destroyed_in_openbw";
                send("combat.event",{{"id",session_+":"+std::to_string(frame)+":destruction:"+std::to_string(++event_)},
                    {"entity_id",id},{"proxy_id","openbw:"+std::to_string(target.proxyID)},
                    {"type","destruction"},{"health",0}},revision_,frame);
                std::cerr << "[world] target destroyed id=" << id << " frame=" << frame << std::endl;
            }
        }
        if (frame%24==0 && !std::getenv("BRIDGE_DISABLE_ASSAULT_AI") && assault_.active(frame)) assaultAI(game);
        for (auto unit:game->getAllUnits()) {
            if (unit && unit->exists() && worldUnitType(unit->getType()) && unit->isAttackFrame())
                ++attackFrames_[unit->getID()];
            if (unit && unit->exists() && unit->getType() == BWAPI::UnitTypes::Terran_Medic
                && unit->getOrder() == BWAPI::Orders::MedicHeal) {
                auto target = unit->getOrderTarget();
                if (target && target->exists() && target->isBeingHealed()) {
                    const bool firstPulse = !lastHealFrame_.count(unit->getID())
                        || frame - lastHealFrame_[unit->getID()] > 4;
                    lastHealFrame_[unit->getID()] = frame;
                    if (firstPulse && (std::getenv("BRIDGE_TEST_MEDIC_VULTURE_NATIVE")
                        || std::getenv("BRIDGE_TEST_MEDIC_CAPTURE_DAMAGE")))
                        std::cerr << "[next-tech] role=publisher stage=heal_visual"
                                  << " frame=" << frame << " medic=" << unit->getID()
                                  << " target=" << target->getID()
                                  << " hp=" << target->getHitPoints()
                                  << " energy=" << unit->getEnergy() << std::endl;
                }
            }
        }
        if (frame%3==0) publishActors(game,frame);
    }
private:
    void connect(BWAPI::Game* game) {
        const int fd=::socket(AF_INET,SOCK_STREAM,0); if (fd<0) return;
        sockaddr_in address{}; address.sin_family=AF_INET; address.sin_port=htons(40011); address.sin_addr.s_addr=htonl(INADDR_LOOPBACK);
        if (::connect(fd,reinterpret_cast<sockaddr*>(&address),sizeof(address))!=0) { ::close(fd); return; }
        ::fcntl(fd,F_SETFL,::fcntl(fd,F_GETFL,0)|O_NONBLOCK); socket_=fd;
        send("world.hello",{{"capabilities",{"snapshot","combat.event","navigation.obstacle.remove"}},
            {"map_width",game->mapWidth()},{"map_height",game->mapHeight()}},1,0);
        std::cerr << "[world] connected to bridge service" << std::endl;
    }
    void disconnect() { if (socket_>=0) ::close(socket_); socket_=-1; incoming_.clear(); outgoing_.clear(); pendingRemovals_.clear(); publishedActors_.clear(); publishedActorStates_.clear(); maskReceiver_.reset(); maskValid_=false; pendingMask_.clear(); pendingMaskHash_.clear(); stagedMask_.clear(); stagedMaskHash_.clear(); for (auto& [key, spawn] : nativeSpawns_) spawn.reported=false; for (auto& [id, target] : targets_) if (target.lifecycle=="destroyed_in_openbw") target.reported=false; ready_=false; }
    void flush() {
        while (socket_>=0 && !outgoing_.empty()) {
            const ssize_t n=::send(socket_,outgoing_.data(),outgoing_.size(),MSG_NOSIGNAL);
            if (n>0) outgoing_.erase(0,static_cast<size_t>(n));
            else if (n<0 && (errno==EAGAIN || errno==EWOULDBLOCK)) return;
            else { disconnect(); return; }
        }
    }
    void send(const std::string& kind,const json& payload,uint64_t revision,int frame,long long buildUS=0) {
        const bool measured = kind == "combat.snapshot" && bridge_perf::output("publisher") != nullptr;
        const auto serializeStart = measured ? bridge_perf::nowNS() : 0;
        const json message={{"v",1},{"kind",kind},{"session",session_.empty()?"openbw-startup":session_},
            {"op_id","openbw:"+std::to_string(++sequence_)},{"source","openbw"},
            {"revision",revision},{"bw_tick",frame},{"payload",payload}};
        const auto serialized = message.dump();
        const auto writeStart = measured ? bridge_perf::nowNS() : 0;
        outgoing_+=serialized+"\n"; flush();
        if (measured)
            bridge_perf::snapshot("publisher", payload.value("seq",0ULL), frame,
                payload.value("unit_total",0), payload.value("unit_omitted",0), serialized.size()+1,
                buildUS, (writeStart-serializeStart)/1000,
                (bridge_perf::nowNS()-writeStart)/1000, outgoing_.size());
    }
    void ack(const json& message,bool accepted,const std::string& error="") {
        send("world.ack",{{"op_id",message.at("op_id")},{"accepted",accepted},{"error",error}},
             message.at("revision").get<uint64_t>(),0);
    }
    void handle(BWAPI::Game* game,const json& message) {
        if (message.value("v",0)!=1 || !message.contains("payload") || !message.contains("op_id")) return;
        const std::string kind=message.value("kind","");
        const auto& payload=message.at("payload");
        if (kind=="world.ack") return;
        if (kind=="combat.command") {
            const std::string commandID = payload.value("command_id", "");
            const std::string prefix = session_ + ":";
            const std::string serial = commandID.compare(0, prefix.size(), prefix) == 0
                ? commandID.substr(prefix.size()) : "";
            bool accepted = !session_.empty() && ready_ && game->self()
                && message.value("source", "") == "bridge"
                && message.value("session", "") == session_
                && message.at("revision").get<uint64_t>() == revision_
                && payload.value("verb", "") == "unit.train"
                && payload.value("unit_ids", json::array()).empty()
                && !serial.empty() && serial.size() <= 20
                && serial.find_first_not_of("0123456789") == std::string::npos;
            std::string reason = accepted ? "ok" : "invalid_command";
            uint64_t number = 0;
            if (accepted) {
                try { number = std::stoull(serial); }
                catch (...) { accepted = false; reason = "invalid_command"; }
                if (accepted && number <= lastCommandSerial_) {
                    accepted = false; reason = "duplicate_command";
                }
            }
            BWAPI::Unit target = nullptr;
            const auto targetID = payload.value("target_id", "");
            const auto* requested = worldUnitType(payload.value("unit_type", ""));
            if (accepted) {
                const auto found = targets_.find(targetID);
                if (found != targets_.end()) target = found->second.unit;
                if (!target || !target->exists() || !requested
                    || found->second.lifecycle != "active"
                    || payload.value("target_proxy_id", "") !=
                        "openbw:" + std::to_string(found->second.proxyID)
                    || target->getPlayer() != game->self() || !target->isCompleted()
                    || target->getHitPoints() < 1) {
                    accepted = false; reason = "production_unavailable";
                } else {
                    const auto* building = worldBuildingType(target->getType());
                    if (!building || !worldCanProduce(*building, requested->id)) {
                        accepted = false; reason = "unsupported_unit_type";
                    }
                }
            }
            if (accepted) {
                lastCommandSerial_ = number;
                accepted = target->canTrain(requested->native)
                    && target->train(requested->native);
                if (!accepted) reason = "native_train_rejected";
                std::cerr << "[world] native production command=" << commandID
                          << " building=" << target->getID() << " unit_type=" << requested->id
                          << " accepted=" << accepted << " frame=" << game->getFrameCount()
                          << " minerals=" << game->self()->minerals() << std::endl;
            }
            send("combat.result", {{"command_id", commandID},
                {"player_id", payload.value("player_id", -1)},
                {"request_id", payload.value("request_id", -1)},
                {"accepted", accepted}, {"reason", reason}}, revision_, game->getFrameCount());
            return;
        }
        if (kind=="navigation.mask.cancel") {
            const auto revision = message.at("revision").get<uint64_t>();
            const auto hash = payload.value("hash", "");
            if (message.value("session", "") == session_) {
                if (stagedMaskRevision_ == revision && stagedMaskHash_ == hash) {
                    stagedMask_.clear(); stagedMaskHash_.clear();
                }
                if (pendingMaskRevision_ == revision && pendingMaskHash_ == hash) {
                    pendingMask_.clear(); pendingMaskHash_.clear();
                }
                if (maskRevision_ == revision && maskHash_ == hash) {
                    maskValid_ = false; maskReceiver_.reset();
                }
            }
            ack(message,true); return;
        }
        if (kind=="navigation.mask.begin") {
            const bool valid = message.value("session", "") == session_
                && message.at("revision").get<uint64_t>() >= revision_
                && payload.value("width", 0) == game->mapWidth()
                && payload.value("height", 0) == game->mapHeight()
                && (payload.value("apply_frame", 0) == 0
                    || payload.value("apply_frame", 0) >= game->getFrameCount() + 2)
                && maskReceiver_.begin(payload.value("width", 0), payload.value("height", 0),
                    payload.value("chunks", 0), payload.value("hash", ""));
            maskValid_ = valid;
            maskHash_ = payload.value("hash", "");
            maskRevision_ = message.at("revision").get<uint64_t>();
            maskApplyFrame_ = payload.value("apply_frame", 0);
            maskStageOnly_ = payload.value("stage_only", false);
            if (valid && !maskStageOnly_) {
                stagedMask_.clear(); stagedMaskHash_.clear();
                pendingMask_.clear(); pendingMaskHash_.clear();
            }
            if (!valid) maskReceiver_.reset();
            return;
        }
        if (kind=="navigation.mask.chunk") {
            if (!maskValid_ || message.value("session", "") != session_
                || message.at("revision").get<uint64_t>() != maskRevision_
                || !maskReceiver_.chunk(payload.value("index", -1), payload.value("hex", ""))) {
                maskValid_ = false; maskReceiver_.reset();
            }
            return;
        }
        if (kind=="navigation.mask.end") {
            std::vector<uint8_t> blocked;
            const bool valid = maskValid_ && message.value("session", "") == session_
                && message.at("revision").get<uint64_t>() == maskRevision_
                && payload.value("hash", "") == maskHash_
                && maskReceiver_.finish(blocked);
            maskValid_ = false;
            if (valid) {
                if (maskStageOnly_) {
                    const bool occupied = candidateOverlapsMobile(game, blocked);
                    if (!occupied) {
                        stagedMask_ = std::move(blocked);
                        stagedMaskHash_ = maskHash_;
                        stagedMaskRevision_ = maskRevision_;
                        stagedMaskUnchanged_ = false;
                    }
                    send("navigation.mask.staged", {{"hash",maskHash_},{"accepted",!occupied},
                        {"error",occupied ? "occupied_construction_geometry" : ""}},
                        maskRevision_, game->getFrameCount());
                } else {
                    pendingMask_ = std::move(blocked);
                    pendingMaskHash_ = maskHash_;
                    pendingMaskRevision_ = maskRevision_;
                    pendingMaskFrame_ = maskApplyFrame_;
                }
            } else {
                maskReceiver_.reset();
                send("navigation.mask.applied", {{"hash",maskHash_},{"accepted",false},
                    {"error","invalid_navigation_mask"}}, maskRevision_, game->getFrameCount());
            }
            return;
        }
        if (kind=="navigation.revision.stage") {
            const auto hash = payload.value("hash", "");
            const bool accepted = message.value("session", "") == session_
                && message.at("revision").get<uint64_t>() == revision_ + 1
                && hash == appliedMaskHash_ && pendingMaskHash_.empty();
            if (accepted) {
                stagedMask_.clear(); stagedMaskHash_ = hash;
                stagedMaskRevision_ = revision_ + 1; stagedMaskUnchanged_ = true;
            }
            send("navigation.mask.staged", {{"hash",hash},{"accepted",accepted},
                {"error",accepted ? "" : "stale_or_unknown_navigation_hash"}},
                message.at("revision").get<uint64_t>(), game->getFrameCount());
            return;
        }
        if (kind=="navigation.mask.schedule") {
            const auto hash = payload.value("hash", "");
            const int frame = payload.value("apply_frame", 0);
            const bool accepted = message.value("session", "") == session_
                && message.at("revision").get<uint64_t>() == stagedMaskRevision_
                && hash == stagedMaskHash_ && frame >= game->getFrameCount() + 24;
            if (accepted) {
                pendingMask_ = stagedMask_; pendingMaskHash_ = stagedMaskHash_;
                pendingMaskRevision_ = stagedMaskRevision_; pendingMaskFrame_ = frame;
                pendingMaskUnchanged_ = stagedMaskUnchanged_;
            }
            send("navigation.mask.scheduled", {{"hash",hash},{"accepted",accepted},
                {"apply_frame",frame},{"error",accepted ? "" : "navigation_schedule_late_or_stale"}},
                message.at("revision").get<uint64_t>(), game->getFrameCount());
            return;
        }
        if (kind=="world.patch.targets") {
            if (message.value("session", "") != session_
                || message.at("revision").get<uint64_t>() != revision_
                || !payload.is_object()) { ack(message,false,"stale_target_patch"); return; }
            try {
                auto next = desired_.entities;
                std::set<std::string> touched;
                const auto removals = payload.at("removals");
                const auto additions = payload.at("additions");
                const auto modifications = payload.at("modifications");
                if (!removals.is_array() || !additions.is_array() || !modifications.is_array()
                    || removals.size()+additions.size()+modifications.size()>4096)
                    throw std::invalid_argument("invalid_target_patch_shape");
                if (liveTargetsResolving_) throw std::invalid_argument("target_patch_in_progress");
                for (const auto& value : removals) {
                    const auto id = value.get<std::string>();
                    if (!touched.insert(id).second || !next.erase(id))
                        throw std::invalid_argument("invalid_target_removal");
                }
                for (const auto& value : additions) {
                    auto entity = starcoaster::parseEntity(value, game->mapWidth(), game->mapHeight());
                    if (!touched.insert(entity.id).second || next.count(entity.id))
                        throw std::invalid_argument("invalid_target_addition");
                    next.emplace(entity.id, std::move(entity));
                }
                for (const auto& value : modifications) {
                    auto entity = starcoaster::parseEntity(value, game->mapWidth(), game->mapHeight());
                    if (!touched.insert(entity.id).second || !next.count(entity.id))
                        throw std::invalid_argument("invalid_target_modification");
                    next[entity.id] = std::move(entity);
                }
                for (const auto& value : removals) retireTarget(game, value.get<std::string>(), "manual_removed");
                for (const auto& value : modifications) {
                    const auto id = value.at("id").get<std::string>();
                    const auto& entity = next.at(id);
                    if (!entity.destructible || !entity.targetable)
                        retireTarget(game, id, "targetability_removed");
                    else for (auto& pending : pending_) if (pending.id == id) pending.id.clear();
                }
                desired_.entities = std::move(next);
                desired_.revision = revision_;
                for (const auto& id : touched) {
                    auto found = desired_.entities.find(id);
                    if (found == desired_.entities.end()) entities_.erase(id);
                    else entities_[id] = found->second.raw;
                }
                unsupported_ = json::array(); unsupportedTotal_ = 0;
                unsupportedReasons_ = json::object();
                std::set<std::string> changed;
                for (const auto& value : additions) changed.insert(value.at("id").get<std::string>());
                for (const auto& value : modifications) changed.insert(value.at("id").get<std::string>());
                requestTargets(game, &changed);
                liveTargetsResolving_ = true;
                liveTargetPatchID_ = payload.at("patch_id").get<std::string>();
                ack(message,true);
                std::cerr << "[world] live targets accepted additions=" << additions.size()
                    << " modifications=" << modifications.size() << " removals=" << removals.size()
                    << " revision=" << revision_ << std::endl;
            } catch (const std::exception& exception) {
                ack(message,false,exception.what());
            }
            return;
        }
        if (kind=="world.snapshot.begin") {
            const int width=payload.at("width"), height=payload.at("height"), chunks=payload.at("chunks");
            std::string error;
            if (!stager_.begin(message.at("session"),message.at("revision"),width,height,chunks,session_,revision_,error)) {
                ack(message,false,error); return;
            }
            ready_=false;
            pendingMask_.clear(); pendingMaskHash_.clear();
            stagedMask_.clear(); stagedMaskHash_.clear();
            assault_.configure(payload.value("objective_id", ""), message.at("session").get<std::string>(),
                payload.value("scenario_mode", "") == "park_defense");
            ack(message,true); return;
        }
        if (kind=="world.start") {
            if (!ready_ || message.value("session", "") != session_) {
                ack(message,false,"world_not_ready"); return;
            }
            if (!assault_.start(game->getFrameCount(), payload.value("delay_frames", 0))) {
                ack(message,false,"scenario_not_configured"); return;
            }
            ack(message,true); return;
        }
        if (kind=="unit.spawn.execute") {
            if (!ready_ || message.value("session", "") != session_
                || message.at("revision").get<uint64_t>() != revision_) {
                ack(message,false,"stale_or_unready_spawn"); return;
            }
            const bool accepted = executeNativeSpawn(game,payload,false);
            ack(message,accepted,accepted ? "" : spawnError_);
            const char* disconnectAt = std::getenv("BRIDGE_TEST_DISCONNECT_SPAWN_INDEX");
            if (accepted && !testSpawnDisconnectInjected_ && disconnectAt && *disconnectAt) {
                char* end = nullptr;
                const long index = std::strtol(disconnectAt, &end, 10);
                if (end && !*end && index >= 0 && index <= 4
                    && payload.value("index", -1) == index) {
                    testSpawnDisconnectInjected_ = true;
                    std::cerr << "[world] injected publisher disconnect after spawn issue index="
                              << index << std::endl;
                    disconnect();
                }
            }
            return;
        }
        if (kind=="unit.spawn.reconcile") {
            if (message.value("session", "") != session_ || !payload.is_object()
                || !payload.contains("pending") || !payload.at("pending").is_array()
                || payload.at("pending").size() > 64) {
                ack(message,false,"invalid_spawn_reconciliation"); return;
            }
            for (const auto& item : payload.at("pending")) {
                if (!item.is_object() || !item.contains("request_id")
                    || !item.at("request_id").is_string() || !item.contains("index")
                    || !item.at("index").is_number_integer()) continue;
                const auto id = item.at("request_id").get<std::string>();
                const int index = item.at("index").get<int>();
                const auto key = id + ":" + std::to_string(index);
                const auto found = nativeSpawns_.find(key);
                if (found == nativeSpawns_.end()) {
                    send("unit.spawn.status", {{"request_id",id}, {"index",index},
                        {"state","not_received"}}, revision_, game->getFrameCount());
                } else if (found->second.state == "issued" || found->second.state == "uncertain") {
                    send("unit.spawn.status", {{"request_id",id}, {"index",index},
                        {"state","uncertain"}, {"reason","native_creation_pending"}},
                        revision_, game->getFrameCount());
                } else found->second.reported = false;
            }
            publishSpawnOutcomes(game->getFrameCount());
            ack(message,true); return;
        }
        if (kind=="world.snapshot.chunk" || kind=="world.snapshot.end") {
            if (!stager_.active() || message.value("session","")!=stager_.session()
                || message.at("revision").get<uint64_t>()!=stager_.revision()) {
                ack(message,false,"stale_or_missing_snapshot"); return;
            }
        } else if (message.value("session","")!=session_ || message.at("revision").get<uint64_t>()<revision_) {
            ack(message,false,"stale_session"); return;
        }
        if (kind=="world.snapshot.chunk") {
            std::string error;
            if (!stager_.chunk(message.at("op_id"),payload.value("index",-1),
                payload.value("entities",json::array()),payload.value("terrain",json::array()),error)) {
                ack(message,false,error); return;
            }
            ack(message,true); return;
        }
        if (kind=="world.snapshot.end") {
            starcoaster::DesiredWorld desired;
            std::string error;
            if (!stager_.finish(payload.value("entities",-1),payload.value("terrain",-1),desired,error)) {
                ack(message,false,error); return;
            }
            reconcile(game,desired); ack(message,true); return;
        }
        if (kind=="combat.result") {
            const auto id=payload.value("entity_id","");
            if (!targets_.count(id)) { ack(message,false,"unknown_entity"); return; }
            const auto state=payload.value("state","");
            if (state=="removal_confirmed") {
                targets_[id].lifecycle="proxy_retired";
                if (targets_[id].unit && targets_[id].unit->exists()) game->removeUnit(targets_[id].unit);
            } else if (state=="removal_failed") targets_[id].lifecycle="park_removal_failed";
            else { ack(message,false,"invalid_result_state"); return; }
            revision_=std::max(revision_,message.at("revision").get<uint64_t>());
            ack(message,true); return;
        }
        if (kind=="navigation.obstacle.remove") {
            const auto id=payload.value("id","");
            if (!entities_.count(id)) { ack(message,false,"unknown_entity"); return; }
            const int applyFrame = payload.value("apply_frame", 0);
            if (applyFrame < game->getFrameCount() + 2) { ack(message,false,"navigation_update_late"); return; }
            pendingRemovals_.push_back({message, id, applyFrame});
            return;
        }
        if (kind=="entity.upsert" || kind=="entity.remove" || kind=="entity.transform" || kind=="entity.state"
            || kind=="navigation.obstacle.upsert" || kind=="navigation.terrain.update") {
            // The contract is understood, but runtime insertion and region
            // rebuilding are deliberately unavailable in world.v1 startup mode.
            ack(message,false,"live_update_unsupported"); return;
        }
        ack(message,false,"unsupported_operation");
    }
    void applyScheduledNavigation(BWAPI::Game* game) {
        if (!pendingMaskHash_.empty() && game->getFrameCount() >= pendingMaskFrame_) {
            const auto rebuildStarted = std::chrono::steady_clock::now();
            const bool onTime = pendingMaskFrame_ == 0 || game->getFrameCount() == pendingMaskFrame_;
            const bool occupied = !pendingMaskUnchanged_ && pendingMaskFrame_ != 0
                && candidateOverlapsMobile(game, pendingMask_);
            const bool applied = onTime && !occupied && (pendingMaskUnchanged_
                || (game->setParkNavigation(pendingMask_) && navigation_.installMask(pendingMask_)));
            if (!pendingMaskUnchanged_) navigation_.markNative(applied);
            if (applied) revision_ = std::max(revision_, pendingMaskRevision_);
            if (applied) appliedMaskHash_ = pendingMaskHash_;
            send("navigation.mask.applied", {{"hash",pendingMaskHash_},{"accepted",applied},
                {"error",applied ? "" : !onTime ? "navigation_update_late" : occupied
                    ? "occupied_construction_geometry" : "native_navigation_update_failed"}},
                pendingMaskRevision_, game->getFrameCount());
            std::cerr << "[world] navigation-mask hash=" << pendingMaskHash_
                      << " frame=" << game->getFrameCount() << " accepted=" << applied
                      << " rebuild_us=" << std::chrono::duration_cast<std::chrono::microseconds>(
                          std::chrono::steady_clock::now() - rebuildStarted).count()
                      << " unchanged=" << pendingMaskUnchanged_ << std::endl;
            pendingMask_.clear(); pendingMaskHash_.clear(); stagedMask_.clear(); stagedMaskHash_.clear();
        }
        for (auto it = pendingRemovals_.begin(); it != pendingRemovals_.end();) {
            if (game->getFrameCount() < it->frame) { ++it; continue; }
            navigation_.remove(it->id);
            const bool applied = game->setParkNavigation(navigation_.mask());
            navigation_.markNative(applied);
            if (applied) revision_ = std::max(revision_, it->message.at("revision").get<uint64_t>());
            std::cerr << "[world] navigation-applied id=" << it->id << " frame=" << game->getFrameCount()
                      << " accepted=" << applied << std::endl;
            ack(it->message, applied, applied ? "" : "native_navigation_update_failed");
            it = pendingRemovals_.erase(it);
        }
    }
    bool candidateOverlapsMobile(BWAPI::Game* game, const std::vector<uint8_t>& candidate) const {
        const auto current = navigation_.mask();
        if (candidate.size() != current.size()) return true;
        const int width = game->mapWidth() * 4;
        for (auto unit : game->getAllUnits()) {
            if (!unit || !unit->exists()) continue;
            const auto type = unit->getType();
            if (!worldUnitType(type)) continue;
            const auto point = unit->getPosition();
            if (point.x < 0 || point.y < 0) continue;
            const size_t index = static_cast<size_t>(point.y / 8) * width + point.x / 8;
            if (index < candidate.size() && candidate[index] && !current[index]) return true;
        }
        return false;
    }
    void reconcile(BWAPI::Game* game, const starcoaster::DesiredWorld& desired) {
        const bool newSession = !session_.empty() && session_ != desired.session;
        // The snapshot contains logical combat footprints, which include
        // overhead ride track. Only the bridge-derived mask may test actor
        // overlap; its staged revision performs that check below.
        if (newSession) { nativeSpawns_.clear(); activeSpawn_.clear(); }
        const auto plan = starcoaster::planReconciliation(desired_, desired);
        for (auto it = targets_.begin(); it != targets_.end();) {
            if (!newSession && desired.entities.count(it->first)
                && it->second.lifecycle == "active"
                && (!it->second.unit || !it->second.unit->exists()
                    || it->second.unit->getHitPoints() <= 0)) {
                it->second.lifecycle = "destroyed_in_openbw";
                it->second.reported = false;
                it->second.lastHP = 0;
            }
            if (newSession || !desired.entities.count(it->first)
                || it->second.lifecycle == "proxy_retired"
                || it->second.lifecycle == "park_removal_failed"
                || (it->second.unit && !it->second.unit->exists()
                    && it->second.lifecycle != "destroyed_in_openbw")) {
                if (it->second.unit && it->second.unit->exists()) game->removeUnit(it->second.unit);
                usedUnits_.erase(it->second.proxyID);
                it = targets_.erase(it);
            } else ++it;
        }
        for (auto& pending : pending_)
            if (newSession || !desired.entities.count(pending.id)) pending.id.clear();
        desired_ = desired;
        if (session_ != desired.session) lastCommandSerial_ = 0;
        session_ = desired.session;
        revision_ = desired.revision;
        width_ = desired.width;
        height_ = desired.height;
        entities_.clear();
        if (newSession || navigation_.mask().empty()) {
            navigation_.replace(desired);
            navigation_.markNative(game->setParkNavigation(navigation_.mask()));
        }
        for (const auto& [id, entity] : desired.entities) {
            entities_[id] = entity.raw;
        }
        unsupported_ = json::array();
        unsupportedTotal_ = 0;
        unsupportedReasons_ = json::object();
        requestTargets(game);
        publishActorReconciliation(game->getFrameCount());
        publishSpawnOutcomes(game->getFrameCount());
        initializing_ = true;
        ready_ = false;
        std::cerr << "[world] reconcile keep=" << plan.keep.size()
                  << " changed=" << plan.changed.size()
                  << " create=" << plan.create.size()
                  << " retire=" << plan.retire.size() << std::endl;
    }
    json runtimeIdentity(const WorldActorRegistry::RuntimeActor& actor) const {
        const auto type = actor.unit->getType();
        return {{"id", "openbw:" + std::to_string(actor.canonical)},
            {"engine", "openbw"},
            {"type", worldUnitType(type)->id},
            {"owner", actor.unit->getPlayer()->getID()},
            {"phase", actor.unit->isCompleted() ? "complete" : "incomplete"},
            {"generation", actor.generation}, {"session", session_}};
    }
    json runtimeBinding(const WorldActorRegistry::RuntimeActor& actor) const {
        return {{"id", "openbw:" + std::to_string(actor.canonical)},
            {"session", session_}, {"generation", actor.generation},
            {"participant", "publisher"}, {"native_id", std::to_string(actor.unit->getID())},
            {"creation_frame", actor.creationFrame}};
    }
    struct PendingCreation { BWAPI::Unit unit = nullptr; int frame = 0, x = 0, y = 0; };
    bool executeNativeSpawn(BWAPI::Game* game, const json& payload, bool fixture) {
        spawnError_ = "invalid_spawn_execution";
        if (!payload.is_object() || !payload.contains("request_id")
            || !payload.at("request_id").is_string() || !payload.contains("unit_type")
            || !payload.at("unit_type").is_string() || !payload.contains("index")
            || !payload.at("index").is_number_integer() || !payload.contains("x")
            || !payload.at("x").is_number_integer() || !payload.contains("y")
            || !payload.at("y").is_number_integer()) return false;
        const std::string requestID = payload.at("request_id").get<std::string>();
        const std::string kind = payload.at("unit_type").get<std::string>();
        const int index = payload.at("index").get<int>();
        const int x = payload.at("x").get<int>(), y = payload.at("y").get<int>();
        if (requestID.empty() || requestID.size() > 128 || index < 0 || index > 4
            || !worldUnitType(kind)) return false;
        const std::string key = requestID + ":" + std::to_string(index);
        if (auto prior = nativeSpawns_.find(key); prior != nativeSpawns_.end()) {
            const auto& spawn = prior->second;
            if (spawn.unitType != kind || spawn.x != x || spawn.y != y || spawn.fixture != fixture) {
                spawnError_ = "conflicting_spawn_execution"; return false;
            }
            prior->second.reported = false;
            return true;
        }
        if (!activeSpawn_.empty()) { spawnError_ = "native_spawn_busy"; return false; }
        if (nativeSpawns_.size() >= 4096) { spawnError_ = "native_spawn_history_full"; return false; }
        const auto type = worldUnitType(kind)->native;
        int& ownerID = spawnOwnerIDs_.try_emplace(kind, -1).first->second;
        // Resolve the native owner once from the starting roster. Later units
        // of the same type may belong to another player; they do not change
        // the authority of an already accepted spawn request stream.
        if (ownerID < 0) {
            for (auto unit : game->getAllUnits()) {
                if (!unit || !unit->exists() || unit->getType() != type || !unit->getPlayer()) continue;
                const int observed = unit->getPlayer()->getID();
                if (ownerID >= 0 && observed != ownerID) {
                    spawnError_ = "ambiguous_native_owner"; return false;
                }
                ownerID = observed;
            }
        }
        // A newly supported type may be absent from the starting roster.
        // Reuse an unambiguous owner of another supported unit of its race.
        if (ownerID < 0) for (auto unit : game->getAllUnits()) {
            if (!unit || !unit->exists() || !unit->getPlayer()) continue;
            const auto* observedType = worldUnitType(unit->getType());
            if (!observedType || std::string(observedType->race) != worldUnitType(kind)->race) continue;
            const int observed = unit->getPlayer()->getID();
            if (ownerID >= 0 && observed != ownerID) {
                spawnError_ = "ambiguous_native_owner"; return false;
            }
            ownerID = observed;
        }
        // Continuous defense starts with no Zerglings. The publisher owns the
        // Zerg player slot even before its first native unit is created.
        if (ownerID < 0 && std::string(worldUnitType(kind)->race) == "zerg" && game->self())
            ownerID = game->self()->getID();
        BWAPI::Player owner = nullptr;
        for (auto player : game->getPlayers())
            if (player && player->getID() == ownerID) owner = player;
        if (!owner) { spawnError_ = "native_owner_unavailable"; return false; }
        const auto position = starcoaster::compactSpawnPosition(x, y, index);
        const int halfWidth = std::max(type.dimensionLeft(), type.dimensionRight()) + 2;
        const int halfHeight = std::max(type.dimensionUp(), type.dimensionDown()) + 2;
        std::vector<starcoaster::Rect> occupied;
        for (auto unit : game->getAllUnits()) {
            if (!unit || !unit->exists() || unit->isFlying()) continue;
            const auto other = unit->getPosition();
            const auto shape = unit->getType();
            occupied.push_back({other.x - shape.dimensionLeft(), other.y - shape.dimensionUp(),
                shape.width(), shape.height()});
        }
        if (!starcoaster::validSpawnPlacement(navigation_, position.x, position.y,
                game->mapWidth(), game->mapHeight(), halfWidth, halfHeight, {})) {
            spawnError_ = "invalid_native_position"; return false;
        }
        if (!starcoaster::validSpawnPlacement(navigation_, position.x, position.y,
                game->mapWidth(), game->mapHeight(), halfWidth, halfHeight, occupied)) {
            spawnError_ = "occupied"; return false;
        }
        for (int sy : {position.y - halfHeight, position.y, position.y + halfHeight})
            for (int sx : {position.x - halfWidth, position.x, position.x + halfWidth})
                if (!game->isWalkable(sx / 8, sy / 8)) {
                    spawnError_ = "native_unwalkable_position"; return false;
                }
        NativeSpawn spawn;
        spawn.requestID = requestID; spawn.index = index; spawn.unitType = kind;
        spawn.x = x; spawn.y = y; spawn.ownerID = owner->getID();
        spawn.issueFrame = game->getFrameCount(); spawn.state = "issued"; spawn.fixture = fixture;
        nativeSpawns_[key] = spawn;
        activeSpawn_ = key;
        // Multiplayer createUnit may queue a synchronized action and return
        // no unit. Only the later native creation event proves success.
        game->createUnit(owner, type, {position.x, position.y});
        std::cerr << "[world] native spawn issued request=" << requestID << " index=" << index
                  << " type=" << kind << " x=" << position.x << " y=" << position.y << std::endl;
        return true;
    }
    void resolveSpawnCandidates() {
        if (activeSpawn_.empty()) return;
        auto& spawn = nativeSpawns_.at(activeSpawn_);
        if (spawn.state != "issued") return;
        std::map<int, std::vector<int>> candidatesByFrame;
        for (const auto& [native, creation] : pendingCreations_) {
            if (!creation.unit || !creation.unit->exists() || !creation.unit->isCompleted()
                || creation.frame < spawn.issueFrame
                || !creation.unit->getPlayer() || creation.unit->getPlayer()->getID() != spawn.ownerID) continue;
            const auto type = creation.unit->getType();
            if (!worldUnitType(spawn.unitType) || type != worldUnitType(spawn.unitType)->native) continue;
            candidatesByFrame[creation.frame].push_back(native);
        }
        if (candidatesByFrame.empty()) return;
        const auto& first = *candidatesByFrame.begin();
        if (first.second.size() != 1) {
            spawn.state = "uncertain"; spawn.reason = "ambiguous_native_creation";
            spawn.reported = false;
            std::cerr << "[world] ambiguous native spawn request=" << spawn.requestID
                      << " frame=" << first.first << " matches=" << first.second.size() << std::endl;
            return;
        }
        const auto creation = pendingCreations_.at(first.second.front());
        const auto expected = starcoaster::compactSpawnPosition(spawn.x, spawn.y, spawn.index);
        // The unit can already be moving when this frame is processed. Match
        // the creation event's position, allowing one tile for native collision
        // resolution, rather than its later position near the park interior.
        if (std::abs(creation.x - expected.x) <= 32 &&
            std::abs(creation.y - expected.y) <= 32)
            spawn.candidateID = first.second.front();
    }
    void registerPendingCreations() {
        if (!actorRegistry_.prepared()) return;
        for (auto it = pendingCreations_.begin(); it != pendingCreations_.end();) {
            const auto creation = it->second;
            if (!creation.unit || !creation.unit->exists()) { it = pendingCreations_.erase(it); continue; }
            if (actorRegistry_.known(creation.unit)) { it = pendingCreations_.erase(it); continue; }
            // Conventional training becomes visible at completion. Types
            // explicitly marked for incomplete presentation (such as eggs)
            // enter the visible registry while native production continues.
            const auto* observedType = worldUnitType(creation.unit->getType());
            if (!observedType || (!creation.unit->isCompleted()
                && !observedType->visibleIncomplete)) { ++it; continue; }
            const int canonical = 3000 + runtimeSerial_ + 1;
            if (!actorRegistry_.registerRuntime(creation.unit, canonical,
                    static_cast<uint64_t>(runtimeSerial_ + 1), creation.frame)) { ++it; continue; }
            ++runtimeSerial_;
            if (!activeSpawn_.empty()) {
                auto& spawn = nativeSpawns_.at(activeSpawn_);
                if (spawn.state == "issued" && spawn.candidateID == creation.unit->getID()) {
                    spawn.state = "created"; spawn.actorID = "openbw:" + std::to_string(canonical);
                    spawn.actualX = creation.x; spawn.actualY = creation.y;
                    spawn.reported = false;
                    activeSpawn_.clear();
                }
            }
            if (testMarineSpawnRequested_ && testMarineCanonical_ == 0
                && creation.unit->getType() == BWAPI::UnitTypes::Terran_Marine)
                testMarineCanonical_ = canonical;
            std::cerr << "[world] actor-spawn id=openbw:" << canonical
                      << " native=" << creation.unit->getID() << " frame=" << creation.frame
                      << " generation=" << runtimeSerial_ << std::endl;
            it = pendingCreations_.erase(it);
        }
    }
    void publishRuntimeEvents(int frame) {
        for (const auto& [canonical, actor] : actorRegistry_.runtime()) {
            if (!actor.unit || !actor.unit->exists()) continue;
            const auto identity = runtimeIdentity(actor);
            const auto nativeID = actor.unit->getID();
            const std::pair<std::string, std::string> state{
                identity.at("type").get<std::string>(), identity.at("phase").get<std::string>()};
            if (!publishedActors_.count(nativeID)) {
                send("actor.spawn", identity, revision_, frame);
                send("actor.bind", runtimeBinding(actor), revision_, frame);
                if (socket_ >= 0) {
                    publishedActors_.insert(nativeID);
                    publishedActorStates_[nativeID] = state;
                }
            } else if (auto prior = publishedActorStates_.find(nativeID);
                       prior != publishedActorStates_.end() && prior->second != state) {
                send("actor.morph", {{"id", identity.at("id")}, {"session", session_},
                    {"generation", actor.generation}, {"from_type", prior->second.first},
                    {"type", state.first}, {"phase", state.second}}, revision_, frame);
                prior->second = state;
            }
        }
    }
    void publishSpawnOutcomes(int frame) {
        if (socket_ < 0 || session_.empty()) return;
        for (auto& [key, spawn] : nativeSpawns_) {
            if (spawn.fixture || spawn.reported || spawn.state == "issued") continue;
            json status = {{"request_id", spawn.requestID}, {"index", spawn.index},
                {"state", spawn.state}};
            if (!spawn.actorID.empty()) {
                status["actor_id"] = spawn.actorID;
                status["x"] = spawn.actualX;
                status["y"] = spawn.actualY;
            }
            if (!spawn.reason.empty()) status["reason"] = spawn.reason;
            send("unit.spawn.status", status, revision_, frame);
            if (socket_ >= 0) spawn.reported = true;
        }
    }
    void publishActorReconciliation(int frame) {
        registerPendingCreations();
        json living = json::array();
        for (const auto& [canonical, actor] : actorRegistry_.runtime())
            if (actor.unit && actor.unit->exists()) living.push_back(runtimeIdentity(actor));
        send("actor.reconcile", {{"living", living}}, revision_, frame);
        for (const auto& [canonical, actor] : actorRegistry_.runtime())
            if (actor.unit && actor.unit->exists()) {
                send("actor.bind", runtimeBinding(actor), revision_, frame);
                publishedActors_.insert(actor.unit->getID());
                const auto identity = runtimeIdentity(actor);
                publishedActorStates_[actor.unit->getID()] = {
                    identity.at("type").get<std::string>(), identity.at("phase").get<std::string>()};
            }
    }
    void retireTarget(BWAPI::Game* game, const std::string& id, const std::string& reason) {
        for (auto& pending : pending_) if (pending.id == id) pending.id.clear();
        auto current = targets_.find(id);
        if (current == targets_.end()) return;
        auto unit = current->second.unit;
        const int proxyID = current->second.proxyID;
        current->second.lifecycle = reason;
        targets_.erase(current);
        usedUnits_.erase(proxyID);
        std::cerr << "[world] target retired id=" << id << " native=" << proxyID
                  << " reason=" << reason << std::endl;
        if (reason == "controlled_replacement")
            send("entity.retire", {{"id",id},{"proxy_id","openbw:"+std::to_string(proxyID)},
                {"reason",reason}}, revision_, game->getFrameCount());
        if (unit && unit->exists()) game->removeUnit(unit);
    }
    void requestTargets(BWAPI::Game* game, const std::set<std::string>* only = nullptr) {
        auto self = game->self();
        auto enemy = targetOwner(game);
        if (self && enemy && !self->isEnemy(enemy)) game->setAlliance(enemy, false, false);
        // Rides are the largest park structures and should remain targetable
        // when a dense park exceeds the configured proxy capacity. The rest
        // retain stable ID order across clients and reconnects.
        std::vector<std::string> ids;
        ids.reserve(entities_.size());
        for (const auto& [id, entity] : entities_) ids.push_back(id);
        std::stable_sort(ids.begin(), ids.end(), [&](const std::string& a, const std::string& b) {
            return (entities_.at(a).value("kind", "") == "ride")
                && (entities_.at(b).value("kind", "") != "ride");
        });
        for (const auto& id : ids) {
            if (only && !only->count(id)) continue;
            const auto& entity = entities_.at(id);
            const auto* building = entity.value("kind", "") == "structure"
                ? worldBuildingType(entity.value("type", "")) : nullptr;
            if (entity.value("kind", "") == "structure" && !building) {
                reportUnsupported(id, "unsupported_native_building_type"); continue;
            }
            if (!entity.value("destructible", false)) continue;
            if (!entity.at("combat").value("targetable", false)) {
                reportUnsupported(id, "not_targetable"); continue;
            }
            if (!enemy && !building) { reportUnsupported(id, "no_enemy_player"); continue; }
            auto current = targets_.find(id);
            if (current != targets_.end()) {
                if (current->second.lifecycle == "destroyed_in_openbw") {
                    send("entity.state", {{"id", id},
                        {"proxy_id", "openbw:"+std::to_string(current->second.proxyID)},
                        {"proxy_x", current->second.x}, {"proxy_y", current->second.y},
                        {"health", 0}}, revision_, game->getFrameCount());
                    continue;
                }
                if (current->second.lifecycle == "park_removal_failed") {
                    reportUnsupported(id, "removal_failed_reconcile_required"); continue;
                }
                if (current->second.lifecycle == "pending_health") continue;
                if (current->second.unit && current->second.unit->exists()) {
                    const auto position = current->second.unit->getPosition();
                    bool nearFootprint = false;
                    for (const auto& rect : entity.at("geometry").value("rects", json::array())) {
                        const int x = rect.at("x"), y = rect.at("y");
                        const int right = x + rect.at("width").get<int>();
                        const int bottom = y + rect.at("height").get<int>();
                        const int dx = std::max({x - position.x, 0, position.x - right});
                        const int dy = std::max({y - position.y, 0, position.y - bottom});
                        if (dx + dy <= 48) { nearFootprint = true; break; }
                    }
                    if ((!building && navigation_.blocked(position.x, position.y, 12))
                        || !nearFootprint) {
                        preservedHP_[id] = current->second.unit->getHitPoints();
                        retireTarget(game, id, "controlled_replacement");
                    } else {
                    const int maximum = entity.at("combat").value("health", 40);
                    if (maximum > 0 && current->second.unit->getHitPoints() > maximum)
                        current->second.unit->setHitPoints(maximum);
                    send("entity.state", {{"id", id},
                        {"proxy_id", "openbw:" + std::to_string(current->second.proxyID)},
                        {"proxy_x", current->second.unit->getPosition().x},
                        {"proxy_y", current->second.unit->getPosition().y},
                        {"health", current->second.unit->getHitPoints()}},
                        revision_, game->getFrameCount());
                    continue;
                    }
                }
            }
            if (std::any_of(pending_.begin(), pending_.end(),
                [&](const PendingTarget& pending) { return pending.id == id; })) continue;
            const auto rects = entity.at("geometry").value("rects", json::array());
            if (rects.empty()) { reportUnsupported(id, "empty_footprint"); continue; }
            int minX = INT_MAX, minY = INT_MAX, maxX = 0, maxY = 0;
            for (const auto& rect : rects) {
                const int x = rect.at("x"), y = rect.at("y");
                const int w = rect.at("width"), h = rect.at("height");
                minX = std::min(minX, x); minY = std::min(minY, y);
                maxX = std::max(maxX, x + w); maxY = std::max(maxY, y + h);
            }
            int x = (minX + maxX) / 2, y = (minY + maxY) / 2;
            if (x < 0 || y < 0 || x >= game->mapWidth() * 32 || y >= game->mapHeight() * 32) {
                reportUnsupported(id, "outside_base_map"); continue;
            }
            if (targets_.size() + pending_.size() >= static_cast<size_t>(targetLimit())) {
                reportUnsupported(id, "configured_target_capacity"); continue;
            }
            if (!building && !findProxyPosition(game, x, y)) {
                reportUnsupported(id, "no_valid_proxy_position"); continue;
            }
            const int health = preservedHP_.count(id) ? preservedHP_.at(id)
                : entity.at("combat").value("health", 40);
            pending_.push_back({id, x, y, health, building ? building->id : "",
                building ? entity.value("owner", -1) : -1});
        }
        std::cerr << "[world] requested targets=" << pending_.size()
                  << " unsupported=" << unsupportedTotal_ << std::endl;
    }
    void resolveTargets(BWAPI::Game* game) {
        auto enemy = targetOwner(game);
        std::set<int> before;
        for (auto unit : game->getAllUnits())
            if (unit && unit->exists()) before.insert(unit->getID());
        for (size_t index = 0; index < pending_.size();) {
            const auto& pending = pending_[index];
            if (!pending.requested) { ++index; continue; }
            BWAPI::Unit found = nullptr;
            for (auto unit : game->getAllUnits()) {
                if (!unit || !unit->exists() || !unit->getPlayer()
                    || (!pending.buildingType.empty()
                        ? unit->getPlayer()->getID() != pending.ownerID
                            || unit->getType() != worldBuildingType(pending.buildingType)->native
                        : unit->getPlayer() != enemy
                            || unit->getType() != BWAPI::UnitTypes::Terran_Civilian)
                    || pending.beforeIDs.count(unit->getID()) || usedUnits_.count(unit->getID())) continue;
                const auto position = unit->getPosition();
                if (std::abs(position.x - pending.x) <= 16 && std::abs(position.y - pending.y) <= 16) {
                    found = unit; break;
                }
            }
            if (found) {
                associateTarget(game, pending, found);
                pending_.erase(pending_.begin() + index);
            } else if (game->getFrameCount() - pending.requestedFrame >= 12) {
                if (!pending.id.empty()) reportUnsupported(pending.id,
                    !pending.buildingType.empty() ? "native_building_not_created" : "proxy_not_created");
                pending_.erase(pending_.begin() + index);
            } else ++index;
        }
        int outstanding = static_cast<int>(std::count_if(pending_.begin(), pending_.end(),
            [](const PendingTarget& pending) { return pending.requested; }));
        for (size_t index = 0; index < pending_.size() && outstanding < 8;) {
            auto& pending = pending_[index];
            if (pending.requested) { ++index; continue; }
            if (pending.id.empty()) { pending_.erase(pending_.begin() + index); continue; }
            const bool nearbyRequest = std::any_of(pending_.begin(), pending_.end(),
                [&](const PendingTarget& other) {
                    return &other != &pending && other.requested
                        && std::abs(other.x - pending.x) <= 48
                        && std::abs(other.y - pending.y) <= 48;
                });
            if (nearbyRequest) { ++index; continue; }
            BWAPI::Player owner = enemy;
            if (!pending.buildingType.empty()) {
                owner = nullptr;
                for (auto player : game->getPlayers())
                    if (player && player->getID() == pending.ownerID
                        && player->getRace() == worldBuildingType(pending.buildingType)->native.getRace()) owner = player;
                if (!owner) {
                    reportUnsupported(pending.id, "native_building_owner_unavailable");
                    pending_.erase(pending_.begin() + index);
                    continue;
                }
                BWAPI::Unit existing = nullptr;
                int matches = 0;
                for (auto unit : game->getAllUnits()) {
                    if (!unit || !unit->exists() || unit->getPlayer() != owner
                        || unit->getType() != worldBuildingType(pending.buildingType)->native
                        || usedUnits_.count(unit->getID())) continue;
                    const auto position = unit->getPosition();
                    if (std::abs(position.x - pending.x) <= 16
                        && std::abs(position.y - pending.y) <= 16) {
                        existing = unit; ++matches;
                    }
                }
                if (matches > 1) {
                    reportUnsupported(pending.id, "ambiguous_native_building");
                    pending_.erase(pending_.begin() + index);
                    continue;
                }
                if (existing) {
                    pending.health = existing->getHitPoints();
                    associateTarget(game, pending, existing);
                    pending_.erase(pending_.begin() + index);
                    continue;
                }
            }
            pending.beforeIDs = before;
            pending.requested = true;
            pending.requestedFrame = game->getFrameCount();
            auto immediate = owner
                ? game->createUnit(owner, !pending.buildingType.empty()
                    ? worldBuildingType(pending.buildingType)->native : BWAPI::UnitTypes::Terran_Civilian,
                    {pending.x, pending.y})
                : nullptr;
            if (immediate) {
                associateTarget(game, pending, immediate);
                pending_.erase(pending_.begin() + index);
            } else { ++outstanding; ++index; }
        }
        if (!pending_.empty()) return;
        if (std::any_of(targets_.begin(), targets_.end(), [](const auto& item) {
            return item.second.lifecycle == "pending_health";
        })) return;
        if (liveTargetsResolving_) {
            liveTargetsResolving_ = false;
            send("world.targets.status", {{"patch_id",liveTargetPatchID_},{"targets",targets_.size()},
                {"unsupported",unsupported_},{"unsupported_total",unsupportedTotal_},
                {"unsupported_reasons",unsupportedReasons_}}, revision_, game->getFrameCount());
            liveTargetPatchID_.clear();
            std::cerr << "[world] live targets resolved revision=" << revision_
                << " targets=" << targets_.size() << " unsupported=" << unsupportedTotal_ << std::endl;
            return;
        }
        initializing_ = false;
        ready_ = unsupportedReasons_.value("removal_failed_reconcile_required", 0) == 0;
        int marines = 0, zerglings = 0;
        for (auto unit : game->getAllUnits()) {
            if (!unit || !unit->exists()) continue;
            if (unit->getType() == BWAPI::UnitTypes::Terran_Marine) ++marines;
            else if (unit->getType() == BWAPI::UnitTypes::Zerg_Zergling) ++zerglings;
        }
        send("world.ready", {{"entities", entities_.size()}, {"targets", targets_.size()},
            {"marines", marines}, {"zerglings", zerglings},
            {"obstacles", navigation_.objects()}, {"navigation", navigation_.capability()},
            {"reconciled", ready_}, {"resuming", everReady_}, {"target_capacity", targetLimit()},
            {"unsupported", unsupported_}, {"unsupported_total", unsupportedTotal_},
            {"unsupported_reasons", unsupportedReasons_}}, revision_, game->getFrameCount());
        if (ready_) everReady_ = true;
        std::cerr << "[world] ready targets=" << targets_.size()
                  << " unsupported=" << unsupportedTotal_ << std::endl;
    }
    void associateTarget(BWAPI::Game* game, const PendingTarget& pending, BWAPI::Unit unit) {
        if (pending.id.empty() || !entities_.count(pending.id)) game->removeUnit(unit);
        else {
            const int desiredHP = std::clamp(pending.health, 1, unit->getType().maxHitPoints());
            if (unit->getHitPoints() != desiredHP) unit->setHitPoints(desiredHP);
            const bool healthReady = unit->getHitPoints() == desiredHP;
            usedUnits_.insert(unit->getID());
            targets_[pending.id] = {pending.id, unit, unit->getID(), unit->getHitPoints(), false, "active",
                unit->getPosition().x, unit->getPosition().y, desiredHP, game->getFrameCount()};
            if (!healthReady) targets_[pending.id].lifecycle = "pending_health";
            preservedHP_.erase(pending.id);
            if (healthReady) send("entity.state", {{"id", pending.id},
                {"proxy_id", "openbw:" + std::to_string(unit->getID())},
                {"proxy_x", unit->getPosition().x},
                {"proxy_y", unit->getPosition().y},
                {"health", unit->getHitPoints()}}, revision_, game->getFrameCount());
            std::cerr << "[world] target id=" << pending.id << " proxy=" << unit->getID()
                      << " type=" << unit->getType().getName()
                      << " hp=" << unit->getHitPoints() << std::endl;
        }
    }
    bool findProxyPosition(BWAPI::Game* game, int& x, int& y) const {
        const int centerX = x, centerY = y;
        const auto available = [&](int px, int py) {
            if (px < 16 || py < 16 || px >= game->mapWidth() * 32 - 16
                || py >= game->mapHeight() * 32 - 16
                || navigation_.blocked(px, py, 12)
                || !game->isWalkable(px / 8, py / 8)) return false;
            for (const auto& pending : pending_)
                if (std::abs(px - pending.x) <= 24 && std::abs(py - pending.y) <= 24) return false;
            for (const auto& [id, target] : targets_)
                if (target.unit && target.unit->exists()
                    && std::abs(px - target.x) <= 24 && std::abs(py - target.y) <= 24) return false;
            return true;
        };
        for (int radius = 0; radius <= 128; radius += 8) {
            for (int dy = -radius; dy <= radius; dy += 8) {
                for (int dx = -radius; dx <= radius; dx += 8) {
                    if (std::max(std::abs(dx), std::abs(dy)) != radius) continue;
                    const int px = centerX + dx, py = centerY + dy;
                    if (available(px, py)) { x = px; y = py; return true; }
                }
            }
        }
        return false;
    }
    int targetLimit() const {
        const char* value = std::getenv("BRIDGE_MAX_TARGETS");
        if (!value || !*value) return 512;
        char* end = nullptr;
        const long parsed = std::strtol(value, &end, 10);
        return end && !*end && parsed >= 1 && parsed <= 1500 ? static_cast<int>(parsed) : 512;
    }
    BWAPI::Player targetOwner(BWAPI::Game* game) const {
        // Neutral ownership prevents Marines from autonomously destroying the
        // park, while explicit native attack orders remain available to both armies.
        return game->neutral();
    }
    void assaultAI(BWAPI::Game* game) {
        BWAPI::Unit objective = nullptr;
        std::vector<BWAPI::Unit> alternatives;
        // Test-only terrain probe: use the existing native assault policy to
        // pursue Marines on the ridge, without changing playable AI orders.
        const bool testRidgeAssault = std::getenv("BRIDGE_TEST_ASSAULT_MARINES") != nullptr;
        for (const auto& [id, target] : targets_) {
            if (target.lifecycle != "active" || !target.unit || !target.unit->exists()) continue;
            if (!testRidgeAssault) {
                alternatives.push_back(target.unit);
                if (id == assault_.objectiveID()) objective = target.unit;
            }
        }
        for (auto unit : game->getAllUnits()) {
            if (!unit || !unit->exists() || unit->getPlayer() == game->self()) continue;
            const auto* kind = worldUnitType(unit->getType());
            if (kind && std::string(kind->ownership) == "player"
                && (assault_.parkDefense() || unit->getType().canAttack()))
                alternatives.push_back(unit);
        }
        assault_.step(game, objective, alternatives);
    }
    void reportUnsupported(const std::string& id,const std::string& reason) {
        ++unsupportedTotal_;
        unsupportedReasons_[reason]=unsupportedReasons_.value(reason,0)+1;
        if (unsupported_.size()<256) unsupported_.push_back(id+":"+reason);
    }
    void publishActors(BWAPI::Game* game,int frame) {
        const auto perfStart = bridge_perf::output("publisher") ? bridge_perf::nowNS() : 0;
        json units=json::array();
        std::set<int> observed;
        int total=0;
        // getAllUnits() follows this participant's vision. A trained Terran
        // unit must still be published when no Zerg scout can see it.
        for (const auto& [canonical, unit] : actorRegistry_.registeredUnits()) {
            if (!unit || !unit->exists()) continue;
            const auto type=unit->getType();
            const auto* definition = worldUnitType(type);
            if (!definition) continue;
            const auto actorID=actorRegistry_.id(unit);
            if (actorID.empty()) continue;
            auto& observedType = observedActorTypes_[unit->getID()];
            if (observedType.first != definition->id) {
                observedType = {definition->id, frame};
            }
            ++total;
            observed.insert(unit->getID());
            if (units.size()>=256) continue;
            const auto position=unit->getPosition();
            const double turns=std::fmod(unit->getAngle()/(2.0*3.14159265358979323846)+1.0,1.0);
            const int facing=static_cast<int>(std::lround(turns*256.0))&255;
            const int hp=std::max(0,unit->getHitPoints());
            auto target=unit->getTarget();
            if (!target) target=unit->getOrderTarget();
            int aimFacing=facing;
            if (target) {
                const auto targetPosition=target->getPosition();
                if (targetPosition.x!=position.x || targetPosition.y!=position.y) {
                    const double aim=std::atan2(targetPosition.y-position.y,targetPosition.x-position.x);
                    aimFacing=static_cast<int>(std::lround(aim*128.0/3.14159265358979323846))&255;
                }
            }
            std::string targetEntity;
            if (target) for (const auto& [id,combat]:targets_)
                if (combat.proxyID==target->getID()) { targetEntity=id; break; }
            const bool healing = type == BWAPI::UnitTypes::Terran_Medic
                && lastHealFrame_.count(unit->getID())
                && frame - lastHealFrame_[unit->getID()] <= 4;
            const char* motion = healing ? "heal" : unit->isAttacking() ? "attack"
                : unit->isMoving() ? "walk" : "idle";
            if (type == BWAPI::UnitTypes::Zerg_Egg)
                motion = frame - observedType.second < 25 ? "morph"
                    : unit->getRemainingBuildTime() == 0 ? "hatch" : "idle";
            json actor={{"id",actorID},
                {"kind",definition->id},
                {"owner",unit->getPlayer()?unit->getPlayer()->getID():0},
                {"x",position.x},{"y",position.y},{"facing",facing},{"aim_facing",aimFacing},
                {"motion",motion}, {"completed",unit->isCompleted()},
                {"remaining_build_frames",unit->getRemainingBuildTime()},
                {"hp",hp},{"max_hp",type.maxHitPoints()},{"alive",true},
                {"energy",unit->getEnergy()},
                {"attack_frames",attackFrames_[unit->getID()]},
                {"target_id",target?json(actorRegistry_.id(target)):json(nullptr)},
                {"target_entity_id",targetEntity.empty()?json(nullptr):json(targetEntity)}};
            units.push_back(actor);
            lastActors_[unit->getID()]={actor,frame};
        }
        for (auto it=lastActors_.begin();it!=lastActors_.end();) {
            if (observed.count(it->first)) { ++it; continue; }
            const auto* deathType = worldUnitType(it->second.first.value("kind", ""));
            if (frame-it->second.second > (deathType ? deathType->deathDisplayFrames : 16)) {
                attackFrames_.erase(it->first);
                lastHealFrame_.erase(it->first);
                observedActorTypes_.erase(it->first);
                it=lastActors_.erase(it); continue;
            }
            if (units.size()<256) {
                json dead=it->second.first;
                dead["motion"]="death"; dead["alive"]=false; dead["hp"]=0;
                if (std::getenv("BRIDGE_TEST_FIREBAT_GAMEPLAY")
                    && dead.value("kind", "") == "terran_firebat")
                    std::cerr << "[firebat-gameplay] role=publisher death_snapshot frame="
                              << frame << " id=" << dead.value("id", "") << std::endl;
                units.push_back(std::move(dead));
            }
            ++it;
        }
        const auto buildUS = perfStart ? (bridge_perf::nowNS()-perfStart)/1000 : 0;
        send("combat.snapshot",{{"seq",++snapshotSequence_},{"bw_tick",frame},
            {"unit_total",total},{"unit_omitted",std::max(0,total-static_cast<int>(units.size()))},
            {"units",units}},revision_,frame,buildUS);
    }
    int socket_=-1,width_=0,height_=0;
    bool ready_=false,initializing_=false; uint64_t revision_=1,sequence_=0,event_=0,snapshotSequence_=0;
    bool everReady_ = false;
    std::string incoming_,outgoing_,session_;
    starcoaster::SnapshotStager stager_;
    starcoaster::DesiredWorld desired_;
    std::map<std::string,json> entities_; std::map<std::string,Target> targets_;
    starcoaster::NavigationAdapter navigation_;
    starcoaster::NavigationMaskReceiver maskReceiver_;
    std::vector<uint8_t> pendingMask_, stagedMask_;
    std::string maskHash_, pendingMaskHash_, stagedMaskHash_, appliedMaskHash_;
    uint64_t maskRevision_ = 0, pendingMaskRevision_ = 0, stagedMaskRevision_ = 0;
    int maskApplyFrame_ = 0, pendingMaskFrame_ = 0;
    bool maskValid_ = false, maskStageOnly_ = false, stagedMaskUnchanged_ = false,
        pendingMaskUnchanged_ = false;
    std::vector<ScheduledRemoval> pendingRemovals_;
    WorldActorRegistry actorRegistry_;
    WorldFirebatTechProbe firebatTechProbe_{false};
    WorldMedicVultureProbe medicVultureProbe_{false};
    WorldGoliathProbe goliathProbe_{false};
    WorldZergProductionProbe zergProductionProbe_{true};
    std::map<int, PendingCreation> pendingCreations_;
    std::set<int> publishedActors_;
    std::map<int, std::pair<std::string, std::string>> publishedActorStates_;
    std::map<std::string, NativeSpawn> nativeSpawns_;
    std::string activeSpawn_, spawnError_;
    std::map<std::string, int> spawnOwnerIDs_;
    int runtimeSerial_ = 0;
    bool testMarineSpawnRequested_ = false;
    int testMarineCanonical_ = 0;
    bool testMarineKillRequested_ = false;
    bool testRuntimeKillRequested_ = false;
    bool testFirebatKillRequested_ = false;
    bool testSpawnDisconnectInjected_ = false;
    WorldAssaultController assault_;
    std::vector<PendingTarget> pending_; std::set<int> usedUnits_; json unsupported_=json::array();
    std::map<std::string,int> preservedHP_;
    bool startingResourcesApplied_ = false;
    std::set<std::string> testBuildingDamageApplied_;
    bool liveTargetsResolving_=false;
    std::string liveTargetPatchID_;
    int unsupportedTotal_=0; json unsupportedReasons_=json::object();
    std::map<int,int> attackFrames_;
    std::map<int,int> lastHealFrame_;
    std::map<int,std::pair<json,int>> lastActors_;
    uint64_t lastCommandSerial_ = 0;
    std::map<int,std::pair<std::string,int>> observedActorTypes_;
};
