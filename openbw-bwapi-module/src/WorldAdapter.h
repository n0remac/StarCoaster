#pragma once

#include <BWAPI.h>
#include <nlohmann/json.hpp>
#include "WorldState.h"
#include "WorldNavigation.h"
#include "WorldActorRegistry.h"
#include "WorldAssaultController.h"

#include <arpa/inet.h>
#include <fcntl.h>
#include <sys/socket.h>
#include <unistd.h>

#include <algorithm>
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
        bool reported = false; std::string lifecycle = "active"; int x = 0, y = 0; };
    struct PendingTarget { std::string id; int x = 0; int y = 0; int health = 0;
        bool requested = false; int requestedFrame = 0; std::set<int> beforeIDs; };
    struct ScheduledRemoval { json message; std::string id; int frame = 0; };
public:
    ~WorldAdapter() { if (socket_ >= 0) ::close(socket_); }
    void onUnitCreate(BWAPI::Unit unit, int frame) {
        if (!unit || !unit->exists() || actorRegistry_.known(unit) || frame < 2) return;
        const auto type = unit->getType();
        if (type != BWAPI::UnitTypes::Terran_Marine && type != BWAPI::UnitTypes::Zerg_Zergling) return;
        pendingCreations_[unit->getID()] = {unit, frame};
    }
    void onUnitDestroy(BWAPI::Unit unit, int frame) {
        if (!unit) return;
        pendingCreations_.erase(unit->getID());
        publishedActors_.erase(unit->getID());
        const auto id = actorRegistry_.id(unit);
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
        std::set<int> pendingIDs;
        for (const auto& [id, creation] : pendingCreations_) pendingIDs.insert(id);
        actorRegistry_.prepare(game, pendingIDs);
        registerPendingCreations();
        if (socket_ < 0) connect(game);
        if (socket_ < 0) return;
        char data[8192];
        for (;;) {
            const ssize_t n = ::recv(socket_, data, sizeof(data), 0);
            if (n > 0) { incoming_.append(data, static_cast<size_t>(n)); if (incoming_.size() > 8388608) { disconnect(); return; } }
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
        flush();
        applyScheduledNavigation(game);
        if (initializing_) resolveTargets(game);
        if (!ready_) return;
        const int frame = game->getFrameCount();
        publishRuntimeEvents(frame);
        const char* spawnAt = std::getenv("BRIDGE_TEST_SPAWN_MARINE_FRAME");
        if (!testMarineSpawnRequested_ && spawnAt && *spawnAt) {
            char* end = nullptr;
            const long requested = std::strtol(spawnAt, &end, 10);
            if (end && !*end && requested > 0 && frame >= requested) {
                testMarineSpawnRequested_ = true;
                BWAPI::Player owner = nullptr;
                for (auto player : game->getPlayers())
                    if (player && player->getRace() == BWAPI::Races::Terran
                        && player->getType() != BWAPI::PlayerTypes::Neutral) owner = player;
                // The reusable 128x128 OpenBW map centers the 64x64 park.
                const int x = (18 + 32) * 32 + 16, y = (30 + 32) * 32 + 16;
                if (owner && x < game->mapWidth() * 32 && y < game->mapHeight() * 32) {
                    game->createUnit(owner, BWAPI::UnitTypes::Terran_Marine, {x, y});
                    std::cerr << "[world] requested native test Marine frame=" << frame
                              << " x=" << x << " y=" << y << std::endl;
                } else std::cerr << "[world] native test Marine fixture unavailable" << std::endl;
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
        for (auto& [id,target] : targets_) {
            const int hp = target.unit && target.unit->exists() ? target.unit->getHitPoints() : 0;
            if (hp != target.lastHP) { target.lastHP=hp; send("entity.state",{{"id",id},{"proxy_id","openbw:"+std::to_string(target.proxyID)},
                {"proxy_x",target.x},{"proxy_y",target.y},{"health",hp}},revision_,frame); }
            if (hp==0 && !target.reported && target.lifecycle=="active") {
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
            if (unit && unit->exists() && (unit->getType()==BWAPI::UnitTypes::Zerg_Zergling
                || unit->getType()==BWAPI::UnitTypes::Terran_Marine) && unit->isAttackFrame())
                ++attackFrames_[unit->getID()];
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
    void disconnect() { if (socket_>=0) ::close(socket_); socket_=-1; incoming_.clear(); outgoing_.clear(); pendingRemovals_.clear(); publishedActors_.clear(); ready_=false; }
    void flush() {
        while (socket_>=0 && !outgoing_.empty()) {
            const ssize_t n=::send(socket_,outgoing_.data(),outgoing_.size(),MSG_NOSIGNAL);
            if (n>0) outgoing_.erase(0,static_cast<size_t>(n));
            else if (n<0 && (errno==EAGAIN || errno==EWOULDBLOCK)) return;
            else { disconnect(); return; }
        }
    }
    void send(const std::string& kind,const json& payload,uint64_t revision,int frame) {
        const json message={{"v",1},{"kind",kind},{"session",session_.empty()?"openbw-startup":session_},
            {"op_id","openbw:"+std::to_string(++sequence_)},{"source","openbw"},
            {"revision",revision},{"bw_tick",frame},{"payload",payload}};
        outgoing_+=message.dump()+"\n"; flush();
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
        if (kind=="world.snapshot.begin") {
            const int width=payload.at("width"), height=payload.at("height"), chunks=payload.at("chunks");
            std::string error;
            if (!stager_.begin(message.at("session"),message.at("revision"),width,height,chunks,session_,revision_,error)) {
                ack(message,false,error); return;
            }
            ready_=false;
            assault_.configure(payload.value("objective_id", ""));
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
    void reconcile(BWAPI::Game* game, const starcoaster::DesiredWorld& desired) {
        const bool newSession = !session_.empty() && session_ != desired.session;
        const auto plan = starcoaster::planReconciliation(desired_, desired);
        for (auto it = targets_.begin(); it != targets_.end();) {
            if (newSession || !desired.entities.count(it->first)
                || it->second.lifecycle == "proxy_retired"
                || it->second.lifecycle == "park_removal_failed"
                || (it->second.unit && !it->second.unit->exists())) {
                if (it->second.unit && it->second.unit->exists()) game->removeUnit(it->second.unit);
                usedUnits_.erase(it->second.proxyID);
                it = targets_.erase(it);
            } else ++it;
        }
        for (auto& pending : pending_)
            if (newSession || !desired.entities.count(pending.id)) pending.id.clear();
        desired_ = desired;
        session_ = desired.session;
        revision_ = desired.revision;
        width_ = desired.width;
        height_ = desired.height;
        entities_.clear();
        navigation_.replace(desired);
        navigation_.markNative(game->setParkNavigation(navigation_.mask()));
        for (const auto& [id, entity] : desired.entities) {
            entities_[id] = entity.raw;
        }
        unsupported_ = json::array();
        unsupportedTotal_ = 0;
        unsupportedReasons_ = json::object();
        requestTargets(game);
        publishActorReconciliation(game->getFrameCount());
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
            {"type", type == BWAPI::UnitTypes::Terran_Marine ? "terran_marine" : "zerg_zergling"},
            {"owner", actor.unit->getPlayer()->getID()},
            {"generation", actor.generation}, {"session", session_}};
    }
    json runtimeBinding(const WorldActorRegistry::RuntimeActor& actor) const {
        return {{"id", "openbw:" + std::to_string(actor.canonical)},
            {"session", session_}, {"generation", actor.generation},
            {"participant", "publisher"}, {"native_id", std::to_string(actor.unit->getID())},
            {"creation_frame", actor.creationFrame}};
    }
    struct PendingCreation { BWAPI::Unit unit = nullptr; int frame = 0; };
    void registerPendingCreations() {
        if (!actorRegistry_.prepared()) return;
        for (auto it = pendingCreations_.begin(); it != pendingCreations_.end();) {
            const auto creation = it->second;
            if (!creation.unit || !creation.unit->exists()) { it = pendingCreations_.erase(it); continue; }
            if (actorRegistry_.known(creation.unit)) { it = pendingCreations_.erase(it); continue; }
            const int canonical = 3000 + runtimeSerial_ + 1;
            if (!actorRegistry_.registerRuntime(creation.unit, canonical,
                    static_cast<uint64_t>(runtimeSerial_ + 1), creation.frame)) { ++it; continue; }
            ++runtimeSerial_;
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
            if (!actor.unit || !actor.unit->exists() || publishedActors_.count(actor.unit->getID())) continue;
            send("actor.spawn", runtimeIdentity(actor), revision_, frame);
            send("actor.bind", runtimeBinding(actor), revision_, frame);
            if (socket_ >= 0) publishedActors_.insert(actor.unit->getID());
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
            }
    }
    void requestTargets(BWAPI::Game* game) {
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
            const auto& entity = entities_.at(id);
            if (!entity.value("destructible", false)) continue;
            if (!entity.at("combat").value("targetable", false)) {
                reportUnsupported(id, "not_targetable"); continue;
            }
            if (!enemy) { reportUnsupported(id, "no_enemy_player"); continue; }
            auto current = targets_.find(id);
            if (current != targets_.end()) {
                if (current->second.lifecycle == "park_removal_failed") {
                    reportUnsupported(id, "removal_failed_reconcile_required"); continue;
                }
                if (current->second.unit && current->second.unit->exists()) {
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
            if (!findProxyPosition(game, x, y)) {
                reportUnsupported(id, "no_valid_proxy_position"); continue;
            }
            pending_.push_back({id, x, y, entity.at("combat").value("health", 40)});
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
                if (!unit || !unit->exists() || unit->getPlayer() != enemy
                    || unit->getType() != BWAPI::UnitTypes::Terran_Civilian
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
                if (!pending.id.empty()) reportUnsupported(pending.id, "proxy_not_created");
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
            pending.beforeIDs = before;
            pending.requested = true;
            pending.requestedFrame = game->getFrameCount();
            auto immediate = enemy
                ? game->createUnit(enemy, BWAPI::UnitTypes::Terran_Civilian, {pending.x, pending.y})
                : nullptr;
            if (immediate) {
                associateTarget(game, pending, immediate);
                pending_.erase(pending_.begin() + index);
            } else { ++outstanding; ++index; }
        }
        if (!pending_.empty()) return;
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
            if (pending.health > 0 && pending.health <= 100000) unit->setHitPoints(pending.health);
            usedUnits_.insert(unit->getID());
            targets_[pending.id] = {pending.id, unit, unit->getID(), unit->getHitPoints(), false, "active",
                unit->getPosition().x, unit->getPosition().y};
            send("entity.state", {{"id", pending.id},
                {"proxy_id", "openbw:" + std::to_string(unit->getID())},
                {"proxy_x", unit->getPosition().x},
                {"proxy_y", unit->getPosition().y},
                {"health", unit->getHitPoints()}}, revision_, game->getFrameCount());
            std::cerr << "[world] target id=" << pending.id << " proxy=" << unit->getID() << std::endl;
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
        for (const auto& [id, target] : targets_) {
            if (target.lifecycle != "active" || !target.unit || !target.unit->exists()) continue;
            alternatives.push_back(target.unit);
            if (id == assault_.objectiveID()) objective = target.unit;
        }
        for (auto unit : game->getAllUnits())
            if (unit && unit->exists() && unit->getType() == BWAPI::UnitTypes::Terran_Marine)
                alternatives.push_back(unit);
        assault_.step(game, objective, alternatives);
    }
    void reportUnsupported(const std::string& id,const std::string& reason) {
        ++unsupportedTotal_;
        unsupportedReasons_[reason]=unsupportedReasons_.value(reason,0)+1;
        if (unsupported_.size()<256) unsupported_.push_back(id+":"+reason);
    }
    void publishActors(BWAPI::Game* game,int frame) {
        json units=json::array();
        std::set<int> observed;
        int total=0;
        for (auto unit:game->getAllUnits()) {
            if (!unit || !unit->exists()) continue;
            const auto type=unit->getType();
            if (type!=BWAPI::UnitTypes::Zerg_Zergling && type!=BWAPI::UnitTypes::Terran_Marine) continue;
            ++total;
            observed.insert(unit->getID());
            if (units.size()>=256) continue;
            const auto position=unit->getPosition();
            const double turns=std::fmod(unit->getAngle()/(2.0*3.14159265358979323846)+1.0,1.0);
            const int facing=static_cast<int>(std::lround(turns*256.0))&255;
            const int hp=std::max(0,unit->getHitPoints());
            const auto actorID=actorRegistry_.id(unit);
            if (actorID.empty()) continue;
            auto target=unit->getTarget();
            if (!target) target=unit->getOrderTarget();
            std::string targetEntity;
            if (target) for (const auto& [id,combat]:targets_)
                if (combat.proxyID==target->getID()) { targetEntity=id; break; }
            json actor={{"id",actorID},
                {"kind",type==BWAPI::UnitTypes::Zerg_Zergling?"zerg_zergling":"terran_marine"},
                {"owner",unit->getPlayer()?unit->getPlayer()->getID():0},
                {"x",position.x},{"y",position.y},{"facing",facing},
                {"motion",unit->isAttacking()?"attack":unit->isMoving()?"walk":"idle"},
                {"hp",hp},{"max_hp",type.maxHitPoints()},{"alive",true},
                {"attack_frames",attackFrames_[unit->getID()]},
                {"target_id",target?json(actorRegistry_.id(target)):json(nullptr)},
                {"target_entity_id",targetEntity.empty()?json(nullptr):json(targetEntity)}};
            units.push_back(actor);
            lastActors_[unit->getID()]={actor,frame};
        }
        for (auto it=lastActors_.begin();it!=lastActors_.end();) {
            if (observed.count(it->first)) { ++it; continue; }
            if (frame-it->second.second>16) { attackFrames_.erase(it->first); it=lastActors_.erase(it); continue; }
            if (units.size()<256) {
                json dead=it->second.first;
                dead["motion"]="death"; dead["alive"]=false; dead["hp"]=0;
                units.push_back(std::move(dead));
            }
            ++it;
        }
        send("combat.snapshot",{{"seq",++snapshotSequence_},{"bw_tick",frame},
            {"unit_total",total},{"unit_omitted",std::max(0,total-static_cast<int>(units.size()))},
            {"units",units}},revision_,frame);
    }
    int socket_=-1,width_=0,height_=0;
    bool ready_=false,initializing_=false; uint64_t revision_=1,sequence_=0,event_=0,snapshotSequence_=0;
    bool everReady_ = false;
    std::string incoming_,outgoing_,session_;
    starcoaster::SnapshotStager stager_;
    starcoaster::DesiredWorld desired_;
    std::map<std::string,json> entities_; std::map<std::string,Target> targets_;
    starcoaster::NavigationAdapter navigation_;
    std::vector<ScheduledRemoval> pendingRemovals_;
    WorldActorRegistry actorRegistry_;
    std::map<int, PendingCreation> pendingCreations_;
    std::set<int> publishedActors_;
    int runtimeSerial_ = 0;
    bool testMarineSpawnRequested_ = false;
    int testMarineCanonical_ = 0;
    bool testMarineKillRequested_ = false;
    WorldAssaultController assault_;
    std::vector<PendingTarget> pending_; std::set<int> usedUnits_; json unsupported_=json::array();
    int unsupportedTotal_=0; json unsupportedReasons_=json::object();
    std::map<int,int> attackFrames_;
    std::map<int,std::pair<json,int>> lastActors_;
};
