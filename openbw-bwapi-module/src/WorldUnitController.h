#pragma once

#include <BWAPI.h>
#include <nlohmann/json.hpp>
#include "WorldActorRegistry.h"
#include "WorldNavigation.h"
#include "WorldProductionFixture.h"

#include <arpa/inet.h>
#include <fcntl.h>
#include <sys/socket.h>
#include <unistd.h>

#include <cerrno>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <iostream>
#include <map>
#include <set>
#include <string>
#include <vector>

// Runs in the Terran BWAPI player slot of the same OpenBW multiplayer game.
// Every command is applied in onFrame and BWAPI enforces player ownership.
class WorldUnitController {
    using json = nlohmann::json;
public:
    ~WorldUnitController() { closeSocket(); }
    void onUnitCreate(BWAPI::Unit unit, int frame) {
        if (!unit || !unit->exists() || actorRegistry_.known(unit) || frame < 2) return;
        const auto type = unit->getType();
        if (!worldUnitType(type)) return;
        creationCandidates_[unit->getID()] = {unit, frame};
        std::vector<std::string> pending;
        for (const auto& [id, binding] : publisherBindings_) pending.push_back(id);
        for (const auto& id : pending) tryBind(id);
    }
    void onUnitDestroy(BWAPI::Unit unit) {
        if (!unit) return;
        creationCandidates_.erase(unit->getID());
        actorRegistry_.forget(unit);
    }
    void onFrame(BWAPI::Game* game) {
        if (!startingResourcesApplied_)
            startingResourcesApplied_ = applyWorldProductionFixture(game);
        std::set<int> candidateIDs;
        for (const auto& [id, candidate] : creationCandidates_) candidateIDs.insert(id);
        actorRegistry_.prepare(game, candidateIDs);
        lastObservedFrame_ = game->getFrameCount();
        for (auto it = creationCandidates_.begin(); it != creationCandidates_.end();) {
            if (!it->second.unit || !it->second.unit->exists()) it = creationCandidates_.erase(it);
            else ++it;
        }
        if (socket_ < 0) connect(game);
        if (socket_ < 0) return;
        char bytes[8192];
        for (;;) {
            const ssize_t count = ::recv(socket_, bytes, sizeof(bytes), 0);
            if (count > 0) {
                incoming_.append(bytes, static_cast<size_t>(count));
                if (incoming_.size() > 16777216) { closeSocket(); return; }
            } else if (count == 0) { closeSocket(); return; }
            else if (errno == EAGAIN || errno == EWOULDBLOCK) break;
            else { closeSocket(); return; }
        }
        size_t newline;
        int processed = 0;
        while (processed++ < 32 && (newline = incoming_.find('\n')) != std::string::npos) {
            const auto line = incoming_.substr(0, newline);
            incoming_.erase(0, newline + 1);
            if (line.size() > 16777216) { closeSocket(); return; }
            try { handle(game, json::parse(line)); }
            catch (const std::exception& error) {
                std::cerr << "[world-control] malformed message: " << error.what() << std::endl;
            }
        }
        std::vector<std::string> pendingActors;
        for (const auto& [id, binding] : publisherBindings_) pendingActors.push_back(id);
        for (const auto& id : pendingActors) tryBind(id);
        applyScheduledNavigation(game);
        probeNativeBarracks(game);
        if (!session_.empty() && game->getFrameCount() % 24 == 0) {
            if (game->self()) send("player.resources", session_, revision_ ? revision_ : 1,
                {{"owner", game->self()->getID()}, {"minerals", game->self()->minerals()},
                 {"supply_used", game->self()->supplyUsed()},
                 {"supply_total", game->self()->supplyTotal()}}, game->getFrameCount());
            for (const auto& [id, link] : targetLinks_) {
                for (auto unit : game->getAllUnits()) {
                    if (!unit || !unit->exists()
                        || !worldBuildingType(unit->getType())
                        || "openbw:" + std::to_string(unit->getID()) != link.proxyID) continue;
                    send("building.state", session_, revision_ ? revision_ : 1,
                        {{"id", id}, {"native_id", link.proxyID},
                         {"owner", unit->getPlayer()->getID()},
                         {"health", unit->getHitPoints()},
                         {"queue", unit->getTrainingQueue().size()},
                         {"remaining_frames", unit->getRemainingTrainTime()},
                         {"minerals", unit->getPlayer()->minerals()},
                         {"supply_used", unit->getPlayer()->supplyUsed()},
                         {"supply_total", unit->getPlayer()->supplyTotal()}},
                        game->getFrameCount());
                    break;
                }
            }
        }
        flush();
    }
private:
    void probeNativeBarracks(BWAPI::Game* game) {
        const char* requested = std::getenv("BRIDGE_TEST_NATIVE_BARRACKS_POSITION");
        if (!requested || !*requested || appliedMaskHash_.empty() || !game->self()) return;
        if (!barracksProbeIssued_) {
            char tail = 0;
            if (std::sscanf(requested, "%d,%d%c", &barracksProbeX_, &barracksProbeY_, &tail) != 2)
                return;
            const auto buildable = [&](int x, int y) {
                return game->canBuildHere({(x - 64) / 32, (y - 48) / 32},
                    BWAPI::UnitTypes::Terran_Barracks, nullptr, true);
            };
            const bool requestedBuildable = buildable(barracksProbeX_, barracksProbeY_);
            if (!requestedBuildable && !std::getenv("BRIDGE_TEST_NATIVE_BARRACKS_EXACT")) {
                bool found = false;
                for (int y = 4; y < game->mapHeight() - 4 && !found; y += 2)
                    for (int x = 4; x < game->mapWidth() - 4 && !found; x += 2) {
                        const int px = x * 32 + 64, py = y * 32 + 48;
                        if (buildable(px, py)) {
                            barracksProbeX_ = px; barracksProbeY_ = py; found = true;
                        }
                    }
            }
            barracksProbeIssued_ = true;
            barracksProbeFrame_ = game->getFrameCount();
            game->createUnit(game->self(), BWAPI::UnitTypes::Terran_Barracks,
                {barracksProbeX_, barracksProbeY_});
            std::cerr << "[world-control] barracks-probe issued x=" << barracksProbeX_
                      << " y=" << barracksProbeY_ << " frame=" << barracksProbeFrame_
                      << " requested_buildable=" << requestedBuildable
                      << " selected_buildable=" << buildable(barracksProbeX_, barracksProbeY_)
                      << " walkable=" << game->isWalkable(barracksProbeX_ / 8, barracksProbeY_ / 8)
                      << std::endl;
        }
        if (barracksProbeUnit_ && barracksProbeUnit_->exists()) {
            const auto owner = game->self();
            if (!barracksProbeSupplyIssued_) {
                barracksProbeSupplyIssued_ = true;
                owner->setMinerals(500);
                for (int y = 4; y < game->mapHeight() - 3; y += 2)
                    for (int x = 4; x < game->mapWidth() - 3; x += 2)
                        if (game->canBuildHere({x, y}, BWAPI::UnitTypes::Terran_Supply_Depot,
                                nullptr, true)) {
                            game->createUnit(owner, BWAPI::UnitTypes::Terran_Supply_Depot,
                                {x * 32 + 48, y * 32 + 32});
                            std::cerr << "[world-control] barracks-probe supply_issued x=" << x
                                      << " y=" << y << std::endl;
                            y = game->mapHeight();
                            break;
                        }
            }
            if (!barracksProbeTrainIssued_ && owner->minerals() >= 50
                && owner->supplyTotal() > owner->supplyUsed()) {
                barracksProbeTrainIssued_ = true;
                int count = 0;
                for (auto unit : game->getAllUnits())
                    if (unit && unit->exists() && unit->getPlayer() == owner
                        && unit->getType() == BWAPI::UnitTypes::Terran_Marine
                        && unit->isCompleted()) ++count;
                barracksProbeInitialMarines_ = count;
                const bool accepted = barracksProbeUnit_->train(BWAPI::UnitTypes::Terran_Marine);
                std::cerr << "[world-control] barracks-probe train_issued accepted=" << accepted
                          << " minerals=" << owner->minerals() << " supply="
                          << owner->supplyUsed() << "/" << owner->supplyTotal() << std::endl;
            }
            if (barracksProbeTrainIssued_ && !barracksProbeQueueSeen_
                && !barracksProbeUnit_->getTrainingQueue().empty()) {
                barracksProbeQueueSeen_ = true;
                std::cerr << "[world-control] barracks-probe queue_active remaining="
                          << barracksProbeUnit_->getRemainingTrainTime() << std::endl;
            }
            if (barracksProbeTrainIssued_ && !barracksProbeMarineSeen_) {
                int count = 0;
                for (auto unit : game->getAllUnits())
                    if (unit && unit->exists() && unit->getPlayer() == owner
                        && unit->getType() == BWAPI::UnitTypes::Terran_Marine
                        && unit->isCompleted()) ++count;
                if (count > barracksProbeInitialMarines_) {
                    barracksProbeMarineSeen_ = true;
                    std::cerr << "[world-control] barracks-probe marine_completed count=" << count
                              << " frame=" << game->getFrameCount() << std::endl;
                }
            }
        }
        if (barracksProbeReported_) return;
        for (auto unit : game->getAllUnits()) {
            if (!unit || !unit->exists() || unit->getPlayer() != game->self()
                || unit->getType() != BWAPI::UnitTypes::Terran_Barracks) continue;
            const auto position = unit->getPosition();
            if (std::abs(position.x - barracksProbeX_) > 16
                || std::abs(position.y - barracksProbeY_) > 16) continue;
            barracksProbeReported_ = true;
            barracksProbeUnit_ = unit;
            auto owner = game->self();
            std::cerr << "[world-control] barracks-probe created id=" << unit->getID()
                      << " frame=" << game->getFrameCount() << " hp=" << unit->getHitPoints()
                      << " completed=" << unit->isCompleted() << " minerals=" << owner->minerals()
                      << " supply=" << owner->supplyUsed() << "/" << owner->supplyTotal()
                      << " can_train=" << unit->canTrain(BWAPI::UnitTypes::Terran_Marine)
                      << std::endl;
            owner->setMinerals(500);
            std::cerr << "[world-control] barracks-probe train="
                      << unit->train(BWAPI::UnitTypes::Terran_Marine)
                      << " queue=" << unit->getTrainingQueue().size() << std::endl;
            return;
        }
        if (game->getFrameCount() - barracksProbeFrame_ >= 36) {
            barracksProbeReported_ = true;
            std::cerr << "[world-control] barracks-probe no_native_building" << std::endl;
        }
    }
    struct TargetLink { std::string proxyID; int x = 0, y = 0; };
    struct ScheduledRemoval { json message; std::string id; int frame = 0; };
    struct CreationCandidate { BWAPI::Unit unit = nullptr; int frame = 0; };
    void tryBind(const std::string& id) {
        if (ambiguousActors_.count(id)) return;
        const auto actor = identities_.find(id), published = publisherBindings_.find(id);
        if (actor == identities_.end() || published == publisherBindings_.end() || session_.empty()) return;
        const auto& identity = actor->second;
        const auto& binding = published->second;
        if (binding.value("generation", uint64_t(0)) != identity.value("generation", uint64_t(0))
            || binding.value("session", "") != session_) return;
        const int frame = binding.value("creation_frame", 0);
        if (frame < 1 || lastObservedFrame_ <= frame) return;
        BWAPI::Unit match = nullptr;
        int matches = 0;
        for (const auto& [native, candidate] : creationCandidates_) {
            if (candidate.frame != frame || !candidate.unit || !candidate.unit->exists()
                || !candidate.unit->isCompleted()
                || !candidate.unit->getPlayer()
                || candidate.unit->getPlayer()->getID() != identity.value("owner", -1)) continue;
            const auto* type = worldUnitType(candidate.unit->getType());
            if (!type || identity.value("type", "") != type->id) continue;
            match = candidate.unit; ++matches;
        }
        if (matches != 1) {
            if (matches > 1) {
                ambiguousActors_.insert(id);
                std::cerr << "[world-control] ambiguous actor binding id=" << id
                    << " frame=" << frame << " matches=" << matches << std::endl;
            }
            return;
        }
        int canonical = 0;
        try {
            if (id.compare(0, 7, "openbw:") != 0) return;
            canonical = std::stoi(id.substr(7));
        } catch (...) { return; }
        const uint64_t generation = identity.value("generation", uint64_t(0));
        if (!actorRegistry_.registerRuntime(match, canonical, generation, frame)) return;
        creationCandidates_.erase(match->getID());
        publisherBindings_.erase(id);
        send("actor.bind", session_, revision_, {{"id", id}, {"session", session_},
            {"generation", generation}, {"participant", "controller"},
            {"native_id", std::to_string(match->getID())}, {"creation_frame", frame}});
        std::cerr << "[world-control] actor-bound id=" << id << " native=" << match->getID()
                  << " frame=" << frame << std::endl;
    }
    void connect(BWAPI::Game* game) {
        const int fd = ::socket(AF_INET, SOCK_STREAM, 0);
        if (fd < 0) return;
        sockaddr_in address{};
        address.sin_family = AF_INET;
        address.sin_port = htons(40012);
        address.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
        if (::connect(fd, reinterpret_cast<sockaddr*>(&address), sizeof(address)) != 0) {
            ::close(fd); return;
        }
        ::fcntl(fd, F_SETFL, ::fcntl(fd, F_GETFL, 0) | O_NONBLOCK);
        socket_ = fd;
        send("world.hello", "openbw-controller", 1,
            {{"role", "controller"}, {"player_id", game->self() ? game->self()->getID() : -1}});
        std::cerr << "[world-control] connected" << std::endl;
    }
    void closeSocket() {
        if (socket_ >= 0) ::close(socket_);
        socket_ = -1;
        incoming_.clear(); outgoing_.clear(); session_.clear(); pendingRemovals_.clear(); revision_ = 0;
        maskReceiver_.reset(); maskValid_ = false; pendingMask_.clear(); pendingMaskHash_.clear();
        stagedMask_.clear(); stagedMaskHash_.clear();
    }
    void flush() {
        while (socket_ >= 0 && !outgoing_.empty()) {
            const ssize_t sent = ::send(socket_, outgoing_.data(), outgoing_.size(), MSG_NOSIGNAL);
            if (sent > 0) outgoing_.erase(0, static_cast<size_t>(sent));
            else if (sent < 0 && (errno == EAGAIN || errno == EWOULDBLOCK)) return;
            else { closeSocket(); return; }
        }
    }
    void send(const std::string& kind, const std::string& session, uint64_t revision,
              const json& payload, int frame = 0) {
        json message = {{"v", 1}, {"kind", kind}, {"session", session},
            {"op_id", "controller:" + std::to_string(++sequence_)}, {"source", "openbw"},
            {"revision", revision}, {"bw_tick", frame}, {"payload", payload}};
        outgoing_ += message.dump() + "\n";
        flush();
    }
    void handle(BWAPI::Game* game, const json& message) {
        if (message.value("v", 0) != 1 || message.value("source", "") != "bridge"
            || !message.contains("payload") || !message.contains("op_id")) return;
        const std::string kind = message.value("kind", "");
        if (kind == "world.hello") {
            const auto announced = message.at("session").get<std::string>();
            if (announced != session_) lastCommandSerial_ = 0;
            session_ = announced;
            revision_ = message.at("revision").get<uint64_t>();
            targetLinks_.clear();
            navigation_.reset(game->mapWidth(), game->mapHeight());
            pendingRemovals_.clear();
            maskReceiver_.reset(); maskValid_ = false; pendingMask_.clear(); pendingMaskHash_.clear();
            stagedMask_.clear(); stagedMaskHash_.clear();
            identities_.clear();
            publisherBindings_.clear();
            ambiguousActors_.clear();
            return;
        }
        if (kind == "navigation.mask.cancel") {
            const auto& payload = message.at("payload");
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
            return;
        }
        if (kind == "navigation.mask.begin") {
            const auto& payload = message.at("payload");
            maskValid_ = message.value("session", "") == session_
                && message.at("revision").get<uint64_t>() >= revision_
                && payload.value("width", 0) == game->mapWidth()
                && payload.value("height", 0) == game->mapHeight()
                && (payload.value("apply_frame", 0) == 0
                    || payload.value("apply_frame", 0) >= game->getFrameCount() + 2)
                && maskReceiver_.begin(payload.value("width", 0), payload.value("height", 0),
                    payload.value("chunks", 0), payload.value("hash", ""));
            maskHash_ = payload.value("hash", "");
            maskRevision_ = message.at("revision").get<uint64_t>();
            maskApplyFrame_ = payload.value("apply_frame", 0);
            maskStageOnly_ = payload.value("stage_only", false);
            if (maskValid_ && !maskStageOnly_) {
                stagedMask_.clear(); stagedMaskHash_.clear();
                pendingMask_.clear(); pendingMaskHash_.clear();
            }
            if (!maskValid_) maskReceiver_.reset();
            return;
        }
        if (kind == "navigation.mask.chunk") {
            const auto& payload = message.at("payload");
            if (!maskValid_ || message.value("session", "") != session_
                || message.at("revision").get<uint64_t>() != maskRevision_
                || !maskReceiver_.chunk(payload.value("index", -1), payload.value("hex", ""))) {
                maskValid_ = false; maskReceiver_.reset();
            }
            return;
        }
        if (kind == "navigation.mask.end") {
            const auto& payload = message.at("payload");
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
                    send("navigation.mask.staged", session_, maskRevision_,
                        {{"hash",maskHash_},{"accepted",!occupied},
                         {"error",occupied ? "occupied_construction_geometry" : ""}},
                        game->getFrameCount());
                } else {
                    pendingMask_ = std::move(blocked);
                    pendingMaskHash_ = maskHash_;
                    pendingMaskRevision_ = maskRevision_;
                    pendingMaskFrame_ = maskApplyFrame_;
                }
            } else {
                maskReceiver_.reset();
                send("navigation.mask.applied", session_, maskRevision_,
                    {{"hash",maskHash_},{"accepted",false},{"error","invalid_navigation_mask"}});
            }
            return;
        }
        if (kind == "navigation.revision.stage") {
            const auto& payload = message.at("payload");
            const auto hash = payload.value("hash", "");
            const bool accepted = message.value("session", "") == session_
                && message.at("revision").get<uint64_t>() == revision_ + 1
                && hash == appliedMaskHash_ && pendingMaskHash_.empty();
            if (accepted) {
                stagedMask_.clear(); stagedMaskHash_ = hash;
                stagedMaskRevision_ = revision_ + 1; stagedMaskUnchanged_ = true;
            }
            send("navigation.mask.staged", session_, message.at("revision").get<uint64_t>(),
                {{"hash",hash},{"accepted",accepted},
                 {"error",accepted ? "" : "stale_or_unknown_navigation_hash"}}, game->getFrameCount());
            return;
        }
        if (kind == "navigation.mask.schedule") {
            const auto& payload = message.at("payload");
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
            send("navigation.mask.scheduled", session_, message.at("revision").get<uint64_t>(),
                {{"hash",hash},{"accepted",accepted},{"apply_frame",frame},
                 {"error",accepted ? "" : "navigation_schedule_late_or_stale"}}, game->getFrameCount());
            return;
        }
        if (kind == "actor.spawn") {
            const auto& identity = message.at("payload");
            if (message.value("session", "") != session_ || identity.value("session", "") != session_) return;
            const auto id = identity.value("id", "");
            if (id.empty()) return;
            identities_[id] = identity;
            for (const auto& [canonical, actor] : actorRegistry_.runtime()) {
                if (id != "openbw:" + std::to_string(canonical)
                    || actor.generation != identity.value("generation", uint64_t(0))
                    || !actor.unit || !actor.unit->exists()) continue;
                send("actor.bind", session_, revision_, {{"id", id}, {"session", session_},
                    {"generation", actor.generation}, {"participant", "controller"},
                    {"native_id", std::to_string(actor.unit->getID())},
                    {"creation_frame", actor.creationFrame}});
                return;
            }
            tryBind(id);
            return;
        }
        if (kind == "actor.bind") {
            const auto& binding = message.at("payload");
            if (message.value("session", "") != session_ || binding.value("session", "") != session_
                || binding.value("participant", "") != "publisher") return;
            const auto id = binding.value("id", "");
            if (id.empty()) return;
            publisherBindings_[id] = binding;
            tryBind(id);
            return;
        }
        if (kind == "actor.despawn") {
            const auto id = message.at("payload").value("id", "");
            const auto unit = actorRegistry_.lookup(id);
            if (unit) actorRegistry_.forget(unit);
            identities_.erase(id);
            publisherBindings_.erase(id);
            ambiguousActors_.erase(id);
            return;
        }
        if (kind == "navigation.terrain.update") {
            const auto& payload = message.at("payload");
            const bool valid = !session_.empty() && message.value("session", "") == session_
                && payload.value("width", 0) == game->mapWidth()
                && payload.value("height", 0) == game->mapHeight();
            bool applied = false;
            if (valid) {
                starcoaster::DesiredWorld world;
                world.width = game->mapWidth(); world.height = game->mapHeight();
                world.unwalkableTerrain.assign(static_cast<size_t>(world.width) * world.height, 0);
                for (const auto& cell : payload.value("terrain", json::array())) {
                    const int x = cell.at("x"), y = cell.at("y");
                    if (x < 0 || y < 0 || x >= world.width || y >= world.height) continue;
                    world.unwalkableTerrain[static_cast<size_t>(y) * world.width + x] = 1;
                }
                for (const auto& object : payload.value("obstacles", json::array())) {
                    starcoaster::Entity entity;
                    entity.id = object.at("id").get<std::string>(); entity.blocks = true;
                    for (const auto& rect : object.at("rects"))
                        entity.rectangles.push_back({rect.at("x"), rect.at("y"), rect.at("width"), rect.at("height")});
                    world.entities.emplace(entity.id, std::move(entity));
                }
                navigation_.replace(world);
                applied = game->setParkNavigation(navigation_.mask());
                navigation_.markNative(applied);
            }
            send("world.ack", session_.empty() ? "openbw-controller" : session_,
                revision_ ? revision_ : 1, {{"op_id", message.at("op_id")}, {"accepted", applied},
                    {"error", applied ? "" : "native_navigation_update_failed"}});
            return;
        }
        if (kind == "navigation.obstacle.remove") {
            const auto id = message.at("payload").value("id", "");
            const bool valid = !session_.empty() && message.value("session", "") == session_ && !id.empty();
            const int applyFrame = message.at("payload").value("apply_frame", 0);
            if (!valid || applyFrame < game->getFrameCount() + 2) {
                send("world.ack", session_.empty() ? "openbw-controller" : session_,
                    revision_ ? revision_ : 1, {{"op_id", message.at("op_id")}, {"accepted", false},
                        {"error", valid ? "navigation_update_late" : "invalid_navigation_update"}});
                return;
            }
            pendingRemovals_.push_back({message, id, applyFrame});
            return;
        }
        if (kind == "entity.state" || kind == "entity.remove") {
            const auto& payload = message.at("payload");
            const auto id = payload.value("id", "");
            const bool valid = !session_.empty() && message.value("session", "") == session_
                && message.at("revision").get<uint64_t>() >= revision_ && !id.empty();
            if (valid && kind == "entity.state") {
                const auto proxyID = payload.value("proxy_id", "");
                const int x = payload.value("proxy_x", -1), y = payload.value("proxy_y", -1);
                if (proxyID.compare(0, 7, "openbw:") == 0 && x >= 0 && y >= 0
                    && x < game->mapWidth() * 32 && y < game->mapHeight() * 32)
                    targetLinks_[id] = {proxyID, x, y};
            } else if (valid) targetLinks_.erase(id);
            send("world.ack", session_, revision_ ? revision_ : 1,
                {{"op_id", message.at("op_id")}, {"accepted", valid},
                 {"error", valid ? "" : "stale_target_link"}});
            return;
        }
        if (kind != "combat.command") return;
        const auto& command = message.at("payload");
        const std::string commandID = command.value("command_id", "");
        const std::string verb = command.value("verb", "");
        const auto units = command.value("unit_ids", json::array());
        bool accepted = true;
        std::string reason = "ok";
        if (session_.empty() || message.value("session", "") != session_
            || message.at("revision").get<uint64_t>() < revision_) {
            accepted = false; reason = "stale_session";
        } else if (commandID.empty() || !units.is_array() || units.size() > 32
            || (verb != "unit.train" && units.empty())
            || (verb == "unit.train" && !units.empty())
            || (verb != "unit.move" && verb != "unit.attack" && verb != "unit.attack_move"
                && verb != "unit.hold" && verb != "unit.stop" && verb != "unit.train")) {
            accepted = false; reason = "invalid_command";
        } else if (!validCommandSerial(commandID)) {
            accepted = false; reason = "duplicate_command";
        }
        BWAPI::Unit target = nullptr;
        if (accepted && verb == "unit.train") {
            const std::string requestedType = command.value("unit_type", "terran_marine");
            const auto* requested = worldUnitType(requestedType);
            if (!requested) { accepted = false; reason = "unsupported_unit_type"; }
            const auto targetID = command.value("target_id", "");
            const auto link = targetLinks_.find(targetID);
            if (accepted && (link == targetLinks_.end() || link->second.proxyID
                != command.value("target_proxy_id", ""))) {
                accepted = false; reason = "production_unlinked";
            } else if (accepted) {
                for (auto candidate : game->getAllUnits()) {
                    if (!candidate || !candidate->exists()
                        || "openbw:" + std::to_string(candidate->getID())
                            != link->second.proxyID) continue;
                    const auto position = candidate->getPosition();
                    const auto* building = worldBuildingType(candidate->getType());
                    if (building && worldCanProduce(*building, requestedType)
                        && candidate->getPlayer() == game->self()
                        && candidate->isCompleted() && candidate->getHitPoints() > 0
                        && std::abs(position.x - link->second.x) <= 16
                        && std::abs(position.y - link->second.y) <= 16) target = candidate;
                    break;
                }
                if (!target) { accepted = false; reason = "production_unavailable"; }
            }
        }
        if (accepted && verb == "unit.attack") {
            const auto targetID = command.value("target_id", "");
            if (targetID.compare(0, 7, "openbw:") == 0) target = actorRegistry_.lookup(targetID);
            else {
                const auto link = targetLinks_.find(targetID);
                if (link != targetLinks_.end()) {
                    for (auto candidate : game->getAllUnits()) {
                        if (!candidate || !candidate->exists()
                            || !candidate->getPlayer()
                            || candidate->getPlayer() == game->self()
                            || "openbw:" + std::to_string(candidate->getID())
                                != link->second.proxyID) continue;
                        const auto position = candidate->getPosition();
                        if (std::abs(position.x - link->second.x) <= 16
                            && std::abs(position.y - link->second.y) <= 16) {
                            target = candidate; break;
                        }
                    }
                }
            }
            if (!target || !target->exists() || target->getPlayer() == game->self()) {
                accepted = false; reason = "invalid_target";
            }
        }
        const int x = command.value("x", -1), y = command.value("y", -1);
        if (accepted && (verb == "unit.move" || verb == "unit.attack_move")
            && (x < 0 || y < 0 || x >= game->mapWidth() * 32 || y >= game->mapHeight() * 32)) {
            accepted = false; reason = "invalid_destination";
        }
        std::set<std::string> unique;
        if (accepted) for (const auto& idValue : units) {
            if (!idValue.is_string()) { accepted = false; reason = "invalid_unit"; break; }
            const std::string id = idValue;
            const auto unit = actorRegistry_.lookup(id);
            if (!unique.insert(id).second || !unit || !unit->exists()
                || unit->getPlayer() != game->self()
                || !worldUnitType(unit->getType())
                || !worldUnitType(unit->getType())->controllable) {
                accepted = false; reason = "invalid_owner_or_unit"; break;
            }
        }
        if (accepted) {
            revision_ = message.at("revision").get<uint64_t>();
            lastCommandSerial_ = std::stoull(commandID.substr(session_.size() + 1));
            if (verb == "unit.train") {
                const auto* requested = worldUnitType(command.value("unit_type", "terran_marine"));
                accepted = requested && target->canTrain(requested->native)
                    && target->train(requested->native);
                if (!accepted) reason = "native_train_rejected";
                std::cerr << "[world-control] train command=" << commandID
                          << " barracks=" << target->getID() << " accepted=" << accepted
                          << " queue=" << target->getTrainingQueue().size()
                          << " minerals=" << game->self()->minerals()
                          << " supply=" << game->self()->supplyUsed()
                          << "/" << game->self()->supplyTotal()
                          << " frame=" << game->getFrameCount() << std::endl;
            }
            for (const auto& idValue : units) {
                auto unit = actorRegistry_.lookup(idValue.get<std::string>());
                const auto previousOrder = unit->getOrder().getName();
                bool applied = false;
                if (verb == "unit.move") applied = unit->move({x, y});
                else if (verb == "unit.attack_move") applied = unit->attack({x, y});
                else if (verb == "unit.attack") applied = unit->attack(target);
                else if (verb == "unit.hold") applied = unit->holdPosition();
                else if (verb == "unit.stop") applied = unit->stop();
                if (!applied) { accepted = false; reason = "bwapi_rejected"; }
                std::cerr << "[world-control] command=" << commandID << " unit=" << unit->getID()
                          << " verb=" << verb << " accepted=" << applied
                          << " frame=" << game->getFrameCount()
                          << " order_before=" << previousOrder << " order_after=" << unit->getOrder().getName()
                          << " from=" << unit->getPosition().x << "," << unit->getPosition().y
                          << " to=" << x << "," << y << std::endl;
            }
        }
        send("combat.result", session_.empty() ? "openbw-controller" : session_,
            revision_ ? revision_ : 1,
            {{"command_id", commandID}, {"accepted", accepted}, {"reason", reason},
             {"player_id", command.value("player_id", -1)},
             {"request_id", command.value("request_id", -1)}});
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
            send("navigation.mask.applied", session_, pendingMaskRevision_,
                {{"hash",pendingMaskHash_},{"accepted",applied},
                 {"error",applied ? "" : !onTime ? "navigation_update_late" : occupied
                    ? "occupied_construction_geometry" : "native_navigation_update_failed"}},
                game->getFrameCount());
            std::cerr << "[world-control] navigation-mask hash=" << pendingMaskHash_
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
            std::cerr << "[world-control] navigation-applied id=" << it->id
                      << " frame=" << game->getFrameCount() << " accepted=" << applied << std::endl;
            send("world.ack", session_, revision_ ? revision_ : 1,
                {{"op_id", it->message.at("op_id")}, {"accepted", applied},
                    {"error", applied ? "" : "native_navigation_update_failed"}});
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
    bool validCommandSerial(const std::string& commandID) const {
        const auto prefix = session_ + ":";
        if (commandID.compare(0, prefix.size(), prefix) != 0) return false;
        const auto suffix = commandID.substr(prefix.size());
        if (suffix.empty() || suffix.size() > 20 ||
            suffix.find_first_not_of("0123456789") != std::string::npos) return false;
        try { return std::stoull(suffix) > lastCommandSerial_; }
        catch (...) { return false; }
    }
    int socket_ = -1;
    uint64_t sequence_ = 0, revision_ = 0, lastCommandSerial_ = 0;
    std::string session_, incoming_, outgoing_;
    std::map<std::string, TargetLink> targetLinks_;
    std::vector<ScheduledRemoval> pendingRemovals_;
    WorldActorRegistry actorRegistry_;
    std::map<int, CreationCandidate> creationCandidates_;
    std::map<std::string, json> identities_, publisherBindings_;
    std::set<std::string> ambiguousActors_;
    int lastObservedFrame_ = 0;
    int barracksProbeX_ = 0, barracksProbeY_ = 0, barracksProbeFrame_ = 0;
    bool barracksProbeIssued_ = false, barracksProbeReported_ = false;
    BWAPI::Unit barracksProbeUnit_ = nullptr;
    bool barracksProbeSupplyIssued_ = false, barracksProbeTrainIssued_ = false;
    bool barracksProbeQueueSeen_ = false, barracksProbeMarineSeen_ = false;
    int barracksProbeInitialMarines_ = 0;
    bool startingResourcesApplied_ = false;
    starcoaster::NavigationAdapter navigation_;
    starcoaster::NavigationMaskReceiver maskReceiver_;
    std::vector<uint8_t> pendingMask_, stagedMask_;
    std::string maskHash_, pendingMaskHash_, stagedMaskHash_, appliedMaskHash_;
    uint64_t maskRevision_ = 0, pendingMaskRevision_ = 0, stagedMaskRevision_ = 0;
    int maskApplyFrame_ = 0, pendingMaskFrame_ = 0;
    bool maskValid_ = false, maskStageOnly_ = false, stagedMaskUnchanged_ = false,
        pendingMaskUnchanged_ = false;
};
