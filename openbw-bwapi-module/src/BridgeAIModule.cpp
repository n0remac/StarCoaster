#include <BWAPI.h>
#include "ParkAssaultNavigation.h"

#include <algorithm>

#include <arpa/inet.h>
#include <fcntl.h>
#include <netinet/in.h>
#include <sys/socket.h>
#include <unistd.h>

#include <cerrno>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <iomanip>
#include <iostream>
#include <map>
#include <random>
#include <regex>
#include <sstream>
#include <string>
#include <thread>
#include <tuple>
#include <vector>

namespace {

constexpr double kTau = 6.28318530717958647692;
constexpr size_t kMaxLine = 32768;
constexpr size_t kMaxUnits = 32;

int environmentInteger(const char* name, int fallback) {
    const char* value = std::getenv(name);
    if (!value || !*value) return fallback;
    char* end = nullptr;
    errno = 0;
    const long parsed = std::strtol(value, &end, 10);
    if (errno || !end || *end || parsed < 0 || parsed > 65535) {
        std::cerr << "[bridge] invalid " << name << ": " << value << std::endl;
        return fallback;
    }
    return static_cast<int>(parsed);
}

std::string environmentMapId() {
    const char* value = std::getenv("BRIDGE_MAP_ID");
    const std::string mapId = value && *value ? value : "demo-flat";
    if (mapId.size() > 64 || mapId.empty() ||
        mapId.find_first_not_of("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-") != std::string::npos) {
        std::cerr << "[bridge] invalid BRIDGE_MAP_ID; using demo-flat" << std::endl;
        return "demo-flat";
    }
    return mapId;
}

std::string newSessionId() {
    std::random_device random;
    std::ostringstream result;
    result << std::hex << std::setfill('0');
    for (int i = 0; i < 4; ++i) result << std::setw(8) << random();
    return result.str();
}

int facingByte(double radians) {
    if (!std::isfinite(radians)) return 0;
    double turns = std::fmod(radians, kTau) / kTau;
    if (turns < 0.0) turns += 1.0;
    return static_cast<int>(std::lround(turns * 256.0)) & 255;
}

class LoopbackPublisher {
public:
    ~LoopbackPublisher() { closeAll(); }

    bool start(int port) {
        listener_ = ::socket(AF_INET, SOCK_STREAM, 0);
        if (listener_ < 0) return fail("socket");
        int reuse = 1;
        ::setsockopt(listener_, SOL_SOCKET, SO_REUSEADDR, &reuse, sizeof(reuse));
        if (!nonblocking(listener_)) return fail("fcntl");
        sockaddr_in address{};
        address.sin_family = AF_INET;
        address.sin_port = htons(static_cast<uint16_t>(port));
        address.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
        if (::bind(listener_, reinterpret_cast<sockaddr*>(&address), sizeof(address)) < 0) return fail("bind");
        if (::listen(listener_, 1) < 0) return fail("listen");
        std::cerr << "[bridge] listening on 127.0.0.1:" << port << std::endl;
        return true;
    }

    void poll() {
        if (listener_ < 0) return;
        if (client_ < 0) {
            client_ = ::accept(listener_, nullptr, nullptr);
            if (client_ >= 0) {
                if (!nonblocking(client_)) {
                    disconnect();
                } else {
                    std::cerr << "[bridge] receiver connected" << std::endl;
                }
            } else if (errno != EAGAIN && errno != EWOULDBLOCK) {
                fail("accept");
            }
        }
        flush();
    }

    std::vector<std::string> receiveLines() {
        std::vector<std::string> lines;
        if (client_ < 0) return lines;
        char buffer[512];
        for (;;) {
            const ssize_t count = ::recv(client_, buffer, sizeof(buffer), 0);
            if (count > 0) {
                inbound_.append(buffer, static_cast<size_t>(count));
                if (inbound_.size() > 4096) { disconnect(); return lines; }
            } else if (count == 0) { disconnect(); break; }
            else if (errno == EAGAIN || errno == EWOULDBLOCK) break;
            else { disconnect(); break; }
        }
        size_t newline;
        while ((newline = inbound_.find('\n')) != std::string::npos) {
            if (newline <= 256) lines.push_back(inbound_.substr(0, newline));
            inbound_.erase(0, newline + 1);
        }
        return lines;
    }

    void publish(const std::string& line) {
        if (line.size() > kMaxLine) {
            std::cerr << "[bridge] dropped oversized snapshot bytes=" << line.size() << std::endl;
            return;
        }
        if (client_ < 0) return;
        flush();
        if (!pending_.empty()) return;  // Drop this full snapshot if the receiver is slow.
        pending_ = line;
        pending_.push_back('\n');
        flush();
    }

private:
    static bool nonblocking(int fd) {
        const int flags = ::fcntl(fd, F_GETFL, 0);
        return flags >= 0 && ::fcntl(fd, F_SETFL, flags | O_NONBLOCK) >= 0;
    }

    bool fail(const char* operation) {
        std::cerr << "[bridge] " << operation << " failed: " << std::strerror(errno) << std::endl;
        closeAll();
        return false;
    }

    void flush() {
        while (client_ >= 0 && !pending_.empty()) {
            const ssize_t sent = ::send(client_, pending_.data(), pending_.size(), MSG_NOSIGNAL);
            if (sent > 0) {
                pending_.erase(0, static_cast<size_t>(sent));
            } else if (sent < 0 && (errno == EAGAIN || errno == EWOULDBLOCK)) {
                return;
            } else {
                disconnect();
            }
        }
    }

    void disconnect() {
        if (client_ >= 0) ::close(client_);
        client_ = -1;
        pending_.clear();
        inbound_.clear();
        std::cerr << "[bridge] receiver disconnected" << std::endl;
    }

    void closeAll() {
        if (client_ >= 0) ::close(client_);
        if (listener_ >= 0) ::close(listener_);
        client_ = -1;
        listener_ = -1;
        pending_.clear();
    }

    int listener_ = -1;
    int client_ = -1;
    std::string pending_;
    std::string inbound_;
};

class BridgeAIModule final : public BWAPI::AIModule {
public:
    void onStart() override {
        const int configuredPort = environmentInteger("BRIDGE_PUBLISH_PORT", 39999);
        const int port = configuredPort == 0 ? 39999 : configuredPort;
        const int spawnX = environmentInteger("BRIDGE_SPAWN_X", 320);
        const int spawnY = environmentInteger("BRIDGE_SPAWN_Y", 480);
        const int targetX = environmentInteger("BRIDGE_TARGET_X", 640);
        const int targetY = environmentInteger("BRIDGE_TARGET_Y", 480);
        frameDelayMs_ = environmentInteger("BRIDGE_FRAME_MS", 42);
        siegeStartFrame_ = environmentInteger("BRIDGE_SIEGE_START_FRAME", 48);
        traceBattle_ = std::getenv("BRIDGE_BATTLE_TRACE") != nullptr;
        probeEnemyOrders_ = std::getenv("BRIDGE_PROBE_ENEMY_ORDERS") != nullptr;
        const char* scenario = std::getenv("BRIDGE_SCENARIO");
        battle_ = scenario && std::strcmp(scenario, "battle") == 0;
        frontier_ = scenario && std::strcmp(scenario, "frontier_defense") == 0;
        siege_ = scenario && std::strcmp(scenario, "ride_siege") == 0;
        parkAssault_ = scenario && std::strcmp(scenario, "park_assault") == 0;
        if (scenario && *scenario && !battle_ && !frontier_ && !siege_ && !parkAssault_
            && std::strcmp(scenario, "patrol") != 0) {
            std::cerr << "[bridge] unknown BRIDGE_SCENARIO=" << scenario << std::endl;
            return;
        }
        mapId_ = environmentMapId();
        session_ = newSessionId();
        std::cerr << "[bridge] session=" << session_ << std::endl;
        auto* game = BWAPI::Broodwar.operator->();
        if (!game || game->isReplay() || !game->self()) {
            std::cerr << "[bridge] no active player; unit creation skipped" << std::endl;
            return;
        }
        terranController_ = frontier_ && game->self()->getRace() == BWAPI::Races::Terran;
        if (frontier_ || parkAssault_) {
            // BWAPI otherwise filters getAllUnits() by each faction's fog of war.
            // This observation flag does not change order ownership or OpenBW combat.
            game->enableFlag(BWAPI::Flag::CompleteMapInformation);
            std::cerr << "[frontier] complete-map-observation="
                      << game->isFlagEnabled(BWAPI::Flag::CompleteMapInformation)
                      << " error=" << game->getLastError().toString() << std::endl;
        }
        publisher_.start(terranController_ ? environmentInteger("BRIDGE_COMMAND_PORT", 40000) : port);
        if (parkAssault_) {
            const char* navPath = std::getenv("BRIDGE_NAV_FILE");
            assaultNavReady_ = assaultNav_.load(navPath && *navPath ? navPath : "navigation.grid");
            std::cerr << "[park-assault] navigation-loaded=" << assaultNavReady_
                      << " revision=" << assaultNav_.revision() << std::endl;
            return;
        }
        const int maxX = game->mapWidth() * 32;
        const int maxY = game->mapHeight() * 32;
        if (spawnX >= maxX || spawnY >= maxY || targetX >= maxX || targetY >= maxY) {
            std::cerr << "[bridge] configured coordinates exceed map bounds " << maxX << "x" << maxY << std::endl;
            return;
        }
        if (frontier_) {
            // BWAPI populates complete map observations on the next frame.
            // The game-start callback can still see only initially visible units.
            return;
        }
        if (battle_) {
            startBattle(game, { spawnX, spawnY }, { targetX, targetY });
            return;
        }
        if (siege_) {
            startSiege(game, { spawnX, spawnY },
                       { environmentInteger("BRIDGE_SIEGE_TARGET_X", 736),
                         environmentInteger("BRIDGE_SIEGE_TARGET_Y", 576) });
            return;
        }
        const int requested = environmentInteger("BRIDGE_DEMO_UNITS", 1);
        demoUnits_ = requested >= 1 && requested <= 8 ? requested : 1;
        for (int index = 0; index < demoUnits_; ++index) {
            const int lane = index - (demoUnits_ - 1) / 2;
            const int sx = spawnX + (demoUnits_ == 1 ? 0 : (index % 2) * 20);
            const int sy = spawnY + (demoUnits_ == 1 ? 0 : lane * 18);
            const int tx = targetX - (demoUnits_ == 1 ? 0 : (index % 3) * 24);
            const int targetLane = demoUnits_ == 8 && (index == 0 || index == 7) ? 1 - index : lane;
            const int ty = targetY + (demoUnits_ == 1 ? 0 : targetLane * 18);
            if (sx < 0 || sy < 0 || tx < 0 || ty < 0 || sx >= maxX || sy >= maxY || tx >= maxX || ty >= maxY) {
                std::cerr << "[bridge] squad coordinate outside BW map; index=" << index << std::endl;
                continue;
            }
            BWAPI::Unit unit = game->createUnit(game->self(), BWAPI::UnitTypes::Zerg_Zergling, { sx, sy });
            if (!unit) {
                std::cerr << "[bridge] createUnit failed index=" << index << ": " << game->getLastError().toString() << std::endl;
                continue;
            }
            pending_.push_back({ unit, { sx, sy }, { tx, ty } });
        }
        std::cerr << "[bridge] created squad candidates=" << pending_.size() << std::endl;
    }

    void onFrame() override {
        // The OpenBW launcher does not pace frames when its UI is disabled.
        // Pace its simulation loop here so every third-frame snapshot is about 8 Hz.
        if (frameDelayMs_ > 0) std::this_thread::sleep_for(std::chrono::milliseconds(frameDelayMs_));
        publisher_.poll();
        auto* game = BWAPI::Broodwar.operator->();
        if (!game) return;
        if (frontier_ && !canonicalReady_ && game->getFrameCount() >= 2) prepareCanonicalUnits(game);
        if (terranController_) {
            for (const auto& line : publisher_.receiveLines()) executeMarineOrder(game, line);
            logCombatDigest(game, game->getFrameCount());
            return;
        }
        const int frame = game->getFrameCount();
        if (parkAssault_) {
            for (const auto& line : publisher_.receiveLines()) assaultNavigationUpdate(line);
            if (!assaultReady_ && frame >= 2) startParkAssault(game);
            if (assaultReady_) parkAssaultFrame(game, frame);
            return;
        }
        if (battle_ || frontier_) {
            if (frontier_ && !frontierReady_) {
                if (canonicalReady_) startFrontier(game);
                if (!frontierReady_) return;
            }
            battleFrame(game, frame);
            if (frontier_) logCombatDigest(game, frame);
            return;
        }
        if (siege_) {
            siegeFrame(game, frame);
            return;
        }
        registerPending(game);
        if (demoUnits_ == 8 && !units_.empty()) {
            auto& first = units_.begin()->second;
            if (frame == 850 && first.unit && first.unit->exists()) {
                game->killUnit(first.unit);
                std::cerr << "[bridge] scenario death id=" << units_.begin()->first << std::endl;
            }
        }
        for (auto& [id, patrol] : units_) {
            auto unit = patrol.unit;
            if (!unit || !unit->exists()) continue;
            const auto position = unit->getPosition();
            const int minX = std::min(patrol.spawn.x, patrol.outbound.x) - 40;
            const int maxX = std::max(patrol.spawn.x, patrol.outbound.x) + 40;
            const int minY = std::min(patrol.spawn.y, patrol.outbound.y) - 48;
            const int maxY = std::max(patrol.spawn.y, patrol.outbound.y) + 48;
            if (demoUnits_ == 8 && (position.x < minX || position.x > maxX || position.y < minY || position.y > maxY)
                && frame - patrol.lastCorrectionFrame >= 24) {
                patrol.lastCorrectionFrame = frame;
                unit->stop();
                orderMove(id, patrol, patrol.target);
                std::cerr << "[bridge] corrected patrol id=" << id << " x=" << position.x << " y=" << position.y << std::endl;
            }
            if (demoUnits_ == 8 && id == units_.begin()->first && frame >= 700 && frame < 780) {
                if (frame == 700) unit->stop();
                continue;
            }
            if (demoUnits_ == 8 && id == units_.begin()->first && frame == 780)
                orderMove(id, patrol, patrol.target);
            if (!patrol.initialMoveAccepted) {
                if (frame - patrol.lastMoveAttemptFrame >= 24) {
                    patrol.lastMoveAttemptFrame = frame;
                    patrol.initialMoveAccepted = orderMove(id, patrol, patrol.target);
                }
            } else {
                const auto current = unit->getPosition();
                const int dx = current.x - patrol.target.x;
                const int dy = current.y - patrol.target.y;
                if (!unit->isMoving() && dx * dx + dy * dy <= 16 * 16) {
                    patrol.target = patrol.returning ? patrol.outbound : patrol.spawn;
                    patrol.returning = !patrol.returning;
                    orderMove(id, patrol, patrol.target);
                }
            }
        }
        if (frame % 3 == 0 && frame != lastPublishedFrame_) {
            publish(frame);
            lastPublishedFrame_ = frame;
        }
    }

    void onUnitDestroy(BWAPI::Unit unit) override {
        if (parkAssault_) {
            if (unit) {
                for (auto& [id, target] : assaultTargets_) {
                    if (target.unit && unit->getID() == target.unit->getID() && !target.destroyed) {
                        target.destroyed = true;
                        std::cerr << "[park-assault] target-destroyed id=" << id
                                  << " proxy=" << unit->getID() << " frame="
                                  << BWAPI::Broodwar->getFrameCount() << std::endl;
                    }
                }
                auto found = assaultUnits_.find(unit->getID());
                if (found != assaultUnits_.end()) found->second.alive = false;
            }
            return;
        }
        if (siege_) {
            if (unit && unit->getID() == siegeTargetId_) {
                siegeDestroyed_ = true;
                siegeDestroyFrame_ = BWAPI::Broodwar->getFrameCount();
                std::cerr << "[siege] target-destroyed id=" << siegeTargetId_
                          << " frame=" << siegeDestroyFrame_ << std::endl;
            }
            return;
        }
        if (battle_ || frontier_) {
            if (unit) {
                auto it = battleUnits_.find(unit->getID());
                if (it != battleUnits_.end()) {
                    std::cerr << "[battle] destroyed id=" << it->first << " owner=" << it->second.owner
                              << " kind=" << it->second.kind << " frame=" << BWAPI::Broodwar->getFrameCount() << std::endl;
                    it->second.alive = false;
                    it->second.deathFrame = BWAPI::Broodwar->getFrameCount();
                    queueCombatEvent("death", it->first, 0, it->second.deathFrame);
                }
                if (frontier_ && unit->getID() == siegeTargetId_) {
                    siegeDestroyed_ = true;
                    std::cerr << "[frontier] target-destroyed id=" << siegeTargetId_
                              << " frame=" << BWAPI::Broodwar->getFrameCount() << std::endl;
                    queueCombatEvent("destruction", siegeTargetId_, 0, BWAPI::Broodwar->getFrameCount());
                }
            }
            return;
        }
        if (unit && units_.erase(unit->getID())) {
            std::cerr << "[bridge] unit destroyed id=" << unit->getID() << std::endl;
            publish(BWAPI::Broodwar->getFrameCount());
        }
    }

    void onEnd(bool) override {
        if (battle_ || frontier_ || siege_ || parkAssault_) return;
        units_.clear();
        pending_.clear();
        publish(BWAPI::Broodwar->getFrameCount());
    }

private:
    struct AssaultTarget {
        BWAPI::Unit unit = nullptr;
        int proxyId = -1;
        int initialHp = 0;
        int lastHp = 0;
        bool destroyed = false;
    };
    struct AssaultUnit {
        BWAPI::Unit unit = nullptr;
        std::string squad;
        std::string targetId;
        ParkAssaultNavigation::Point spawn;
        ParkAssaultNavigation::Point approach;
        int launchFrame = 0;
        std::vector<ParkAssaultNavigation::Point> waypoints;
        size_t waypoint = 0;
        int lastOrderFrame = -100;
        int lastProgressFrame = 0;
        ParkAssaultNavigation::Point lastPosition;
        bool attacking = false;
        bool ready = false;
        bool held = false;
        bool rallied = false;
        bool alive = true;
        bool violationLogged = false;
        int attackFrames = 0;
        bool lastAttackFrame = false;
    };

    void assaultNavigationUpdate(const std::string& line) {
        std::istringstream input(line);
        std::string command, session, id, trailing;
        int revision = 0;
        if (!(input >> command >> session >> revision >> id) || input >> trailing
            || command != "nav" || session != session_ || !assaultTargets_.count(id)
            || !assaultTargets_[id].destroyed || !assaultNav_.applyConfirmedDemolition(id, revision)) {
            std::cerr << "[park-assault] rejected-navigation-update " << line << std::endl;
            return;
        }
        std::cerr << "[park-assault] navigation-revision=" << revision << " cleared=" << id << std::endl;
        for (auto& [unitId, tracked] : assaultUnits_) {
            if (!tracked.alive || !tracked.unit || !tracked.unit->exists()) continue;
            assaultPlan(unitId, tracked, BWAPI::Broodwar->getFrameCount(), "demolition");
            std::cerr << "[park-assault] replan id=" << unitId << " reason=demolition"
                      << " waypoints=" << tracked.waypoints.size() << std::endl;
        }
    }

    void startParkAssault(BWAPI::Game* game) {
        if (!assaultNavReady_ || !game->self()) return;
        auto self = game->self();
        const std::vector<std::string> ids = { "carousel-1", "shop-1", "ride-2" };
        std::map<std::string, BWAPI::Unit> found;
        std::map<int, AssaultUnit> zerglings;
        for (auto unit : game->getAllUnits()) {
            if (!unit || !unit->exists()) continue;
            if (unit->getPlayer() == self && unit->getType() == BWAPI::UnitTypes::Zerg_Zergling) {
                const auto p = unit->getPosition();
                AssaultUnit tracked;
                tracked.unit = unit;
                tracked.spawn = { p.x, p.y };
                tracked.lastPosition = tracked.spawn;
                tracked.squad = p.y < 600 ? "beta" : p.x < 650 ? "alpha" : "gamma";
                tracked.targetId = tracked.squad == "alpha" ? ids[0] : tracked.squad == "beta" ? ids[1] : ids[2];
                zerglings.emplace(unit->getID(), tracked);
            }
            if (unit->getType() != BWAPI::UnitTypes::Terran_Barracks
                || !unit->getPlayer() || !self->isEnemy(unit->getPlayer())) continue;
            const auto p = unit->getPosition();
            for (const auto& id : ids) {
                const auto anchor = assaultNav_.target(id);
                if (std::abs(p.x - anchor.x) <= 32 && std::abs(p.y - anchor.y) <= 32) {
                    if (found.count(id)) { std::cerr << "[park-assault] duplicate proxy " << id << std::endl; return; }
                    found[id] = unit;
                }
            }
        }
        if (zerglings.size() != 20 || found.size() != 3) {
            if (!assaultStartWarning_) {
                std::cerr << "[park-assault] waiting fixture zerglings=" << zerglings.size()
                          << " proxies=" << found.size() << std::endl;
                assaultStartWarning_ = true;
            }
            return;
        }
        int squads[3] = { 0, 0, 0 };
        for (auto& [id, unit] : zerglings) {
            const int squad = unit.squad == "alpha" ? 0 : unit.squad == "beta" ? 1 : 2;
            const int ordinal = squads[squad]++;
            const auto anchor = assaultNav_.target(unit.targetId);
            if (squad == 0) unit.approach = { anchor.x - 30 + ordinal % 4 * 20,
                                               anchor.y + 96 + ordinal / 4 * 24 };
            else if (squad == 1) unit.approach = { anchor.x - 96 - ordinal / 3 * 24,
                                                    anchor.y - 20 + ordinal % 3 * 20 };
            else unit.approach = { anchor.x - 24 + ordinal % 3 * 24,
                                   anchor.y + 96 + ordinal / 3 * 24 };
            unit.launchFrame = (squad == 0 ? 12 : squad == 1 ? 36 : 60) + ordinal * 12;
        }
        if (squads[0] != 8 || squads[1] != 6 || squads[2] != 6) {
            std::cerr << "[park-assault] invalid squad sizes " << squads[0] << "," << squads[1]
                      << "," << squads[2] << std::endl;
            return;
        }
        assaultUnits_ = std::move(zerglings);
        for (const auto& id : ids) {
            BWAPI::Unit proxy = found[id];
            assaultTargets_[id] = { proxy, proxy->getID(), proxy->getHitPoints(), proxy->getHitPoints(), false };
            std::cerr << "[park-assault] target-created id=" << id << " proxy=" << proxy->getID()
                      << " hp=" << proxy->getHitPoints() << " x=" << proxy->getPosition().x
                      << " y=" << proxy->getPosition().y << std::endl;
        }
        assaultReady_ = true;
        std::cerr << "[park-assault] initialized zerglings=20 squads=8,6,6 targets=3" << std::endl;
    }

    void assaultPlan(int id, AssaultUnit& tracked, int frame, const char* reason) {
        const auto planningStart = std::chrono::steady_clock::now();
        auto pos = tracked.unit->getPosition();
        const auto destination = tracked.rallied ? tracked.spawn : tracked.approach;
        const ParkAssaultNavigation::Point start{ pos.x, pos.y };
        if (!tracked.rallied && tracked.squad == "beta"
            && pos.y < assaultNav_.target("shop-1").y - 80) {
            const auto shop = assaultNav_.target("shop-1");
            const ParkAssaultNavigation::Point above{ shop.x, shop.y - 128 };
            const ParkAssaultNavigation::Point below{ shop.x, shop.y - 32 };
            tracked.waypoints = assaultNav_.route(start, above);
            auto crossing = assaultNav_.route(above, below);
            auto finish = assaultNav_.route(below, destination);
            if (!crossing.empty() && !tracked.waypoints.empty())
                tracked.waypoints.insert(tracked.waypoints.end(), crossing.begin() + 1, crossing.end());
            if (!finish.empty() && !tracked.waypoints.empty())
                tracked.waypoints.insert(tracked.waypoints.end(), finish.begin() + 1, finish.end());
        } else tracked.waypoints = assaultNav_.route(start, destination);
        tracked.waypoint = tracked.waypoints.size() > 1 ? 1 : 0;
        tracked.lastOrderFrame = -100;
        tracked.lastProgressFrame = frame;
        tracked.lastPosition = { pos.x, pos.y };
        std::cerr << "[park-assault] route id=" << id << " target=" << tracked.targetId
                  << " reason=" << reason << " waypoints=" << tracked.waypoints.size()
                  << " revision=" << assaultNav_.revision() << " microseconds="
                  << std::chrono::duration_cast<std::chrono::microseconds>(
                      std::chrono::steady_clock::now() - planningStart).count() << std::endl;
    }

    void parkAssaultFrame(BWAPI::Game* game, int frame) {
        for (auto& [id, target] : assaultTargets_) {
            const int hp = target.unit && target.unit->exists() ? target.unit->getHitPoints() : 0;
            if (hp < target.lastHp)
                std::cerr << "[park-assault] target-damage id=" << id << " from=" << target.lastHp
                          << " to=" << hp << " frame=" << frame << std::endl;
            target.lastHp = hp;
            if (hp == 0 && !target.destroyed) {
                target.destroyed = true;
                std::cerr << "[park-assault] target-destroyed id=" << id << " proxy="
                          << target.proxyId << " frame=" << frame << std::endl;
            }
        }
        for (auto& [id, tracked] : assaultUnits_) {
            auto unit = tracked.unit;
            if (!tracked.alive || !unit || !unit->exists()) continue;
            const auto pos = unit->getPosition();
            if (frame % 3 == 0)
                std::cerr << "[park-assault] position id=" << id << " x=" << pos.x
                          << " y=" << pos.y << " frame=" << frame
                          << " revision=" << assaultNav_.revision() << std::endl;
            if (frame % 240 == 0 && !tracked.ready)
                std::cerr << "[park-assault] waiting-unit id=" << id << " target=" << tracked.targetId
                          << " x=" << pos.x << " y=" << pos.y
                          << " approach_x=" << tracked.approach.x << " approach_y=" << tracked.approach.y
                          << " waypoint=" << tracked.waypoint << "/" << tracked.waypoints.size() << std::endl;
            if (!assaultNav_.passableBW({ pos.x, pos.y }) && !tracked.violationLogged) {
                tracked.violationLogged = true;
                std::cerr << "[park-assault] COLLISION_VIOLATION id=" << id
                          << " x=" << pos.x << " y=" << pos.y << " frame=" << frame << std::endl;
            }
            const bool attackFrame = unit->isAttackFrame();
            if (attackFrame && !tracked.lastAttackFrame) {
                ++tracked.attackFrames;
                std::cerr << "[park-assault] attack-frame id=" << id << " target="
                          << tracked.targetId << " frame=" << frame << std::endl;
            }
            tracked.lastAttackFrame = attackFrame;
            if (assaultTargets_[tracked.targetId].destroyed && !tracked.rallied) {
                tracked.rallied = true;
                tracked.attacking = false;
                assaultPlan(id, tracked, frame, "target-destroyed");
            }
            if (frame < tracked.launchFrame) continue;
            if (tracked.waypoints.empty()) assaultPlan(id, tracked, frame, "initial");
            if (tracked.waypoints.empty()) continue;
            if (!tracked.rallied && !tracked.attacking && frame >= tracked.launchFrame + 24
                && assaultTargets_[tracked.targetId].unit && assaultTargets_[tracked.targetId].unit->exists()) {
                const auto anchor = assaultNav_.target(tracked.targetId);
                if (std::hypot(pos.x - anchor.x, pos.y - anchor.y) <= 320
                    && assaultNav_.directSafeBW({ pos.x, pos.y }, anchor)) {
                    const bool accepted = unit->attack(assaultTargets_[tracked.targetId].unit);
                    if (accepted) {
                        tracked.attacking = true;
                        tracked.ready = true;
                        std::cerr << "[park-assault] attack-position id=" << id << " target="
                                  << tracked.targetId << " x=" << pos.x << " y=" << pos.y
                                  << " frame=" << frame << std::endl;
                    }
                    std::cerr << "[park-assault] attack-order id=" << id << " target=" << tracked.targetId
                              << " accepted=" << accepted << " frame=" << frame << std::endl;
                    if (accepted) continue;
                }
            }
            if (std::hypot(pos.x - tracked.lastPosition.x, pos.y - tracked.lastPosition.y) >= 8) {
                tracked.lastPosition = { pos.x, pos.y };
                tracked.lastProgressFrame = frame;
            }
            if (!tracked.attacking && !tracked.ready && frame - tracked.lastProgressFrame >= 96) {
                assaultPlan(id, tracked, frame, "stuck");
                std::cerr << "[park-assault] stuck-replan id=" << id << " frame=" << frame << std::endl;
            }
            if (tracked.waypoints.empty()) continue;
            while (tracked.waypoint + 1 < tracked.waypoints.size()) {
                const auto waypoint = tracked.waypoints[tracked.waypoint];
                if (std::hypot(pos.x - waypoint.x, pos.y - waypoint.y) > 12) break;
                ++tracked.waypoint;
                tracked.lastOrderFrame = -100;
            }
            const auto waypoint = tracked.waypoints[tracked.waypoint];
            const double remaining = std::hypot(pos.x - waypoint.x, pos.y - waypoint.y);
            if (tracked.waypoint + 1 == tracked.waypoints.size() && remaining <= 12) continue;
            if (!tracked.attacking && frame - tracked.lastOrderFrame >= 24) {
                const bool accepted = unit->move({ waypoint.x, waypoint.y });
                tracked.lastOrderFrame = frame;
                std::cerr << "[park-assault] move-order id=" << id << " x=" << waypoint.x
                          << " y=" << waypoint.y << " accepted=" << accepted
                          << " frame=" << frame << std::endl;
            }
        }
        if (frame % 3 == 0 && frame != lastPublishedFrame_) {
            publishParkAssault(frame);
            lastPublishedFrame_ = frame;
        }
    }

    void publishParkAssault(int frame) {
        std::ostringstream line;
        line << "{\"v\":3,\"kind\":\"scenario.snapshot\",\"session\":\"" << session_
             << "\",\"map_id\":\"park-assault\",\"seq\":" << ++sequence_
             << ",\"bw_tick\":" << frame << ",\"map_revision\":" << assaultNav_.revision()
             << ",\"units\":[";
        size_t count = 0;
        for (const auto& [id, tracked] : assaultUnits_) {
            auto unit = tracked.unit;
            if (!tracked.alive || !unit || !unit->exists()) continue;
            const auto pos = unit->getPosition();
            const bool moving = unit->isMoving()
                && std::hypot(unit->getVelocityX(), unit->getVelocityY()) >= 0.25;
            if (count++) line << ',';
            line << "{\"id\":\"openbw:" << id << "\",\"kind\":\"zerg_zergling\",\"owner\":"
                 << unit->getPlayer()->getID() << ",\"x\":" << pos.x << ",\"y\":" << pos.y
                 << ",\"facing\":" << facingByte(unit->getAngle()) << ",\"motion\":\""
                 << (unit->isAttacking() ? "attack" : moving ? "walk" : "idle")
                 << "\",\"hp\":" << unit->getHitPoints() << ",\"max_hp\":35,\"alive\":true"
                 << ",\"attack_frames\":" << tracked.attackFrames << ",\"target_id\":";
            auto target = unit->getTarget();
            if (target) line << "\"openbw:" << target->getID() << "\"";
            else line << "null";
            line << '}';
        }
        const size_t actorCount = count;
        line << "],\"targets\":[";
        count = 0;
        for (const auto& [id, target] : assaultTargets_) {
            const int hp = target.unit && target.unit->exists() ? target.unit->getHitPoints() : 0;
            if (count++) line << ',';
            line << "{\"id\":\"" << id << "\",\"proxy_unit_id\":\"openbw:" << target.proxyId
                 << "\",\"hp\":" << hp << ",\"max_hp\":" << target.initialHp
                 << ",\"state\":\"" << (hp == 0 ? "destroyed" : hp < target.initialHp ? "damaged" : "intact") << "\"}";
        }
        line << "],\"events\":[]}";
        if (frame % 24 == 0)
            std::cerr << "[park-assault] snapshot-bytes=" << line.str().size()
                      << " actors=" << actorCount << " frame=" << frame << std::endl;
        publisher_.publish(line.str());
    }

    int canonicalId(int internalId) const {
        if (!frontier_) return internalId;
        const auto found = internalToCanonical_.find(internalId);
        return found == internalToCanonical_.end() ? internalId : found->second;
    }

    void prepareCanonicalUnits(BWAPI::Game* game) {
        std::vector<BWAPI::Unit> marines, zerglings, targets;
        for (auto unit : game->getAllUnits()) {
            if (!unit || !unit->exists()) continue;
            const auto type = unit->getType();
            if (type == BWAPI::UnitTypes::Terran_Marine) marines.push_back(unit);
            if (type == BWAPI::UnitTypes::Zerg_Zergling) zerglings.push_back(unit);
            if (type == BWAPI::UnitTypes::Terran_Missile_Turret) targets.push_back(unit);
        }
        if (marines.size() != 4 || zerglings.size() != 8 || targets.size() != 1) return;
        const auto byPosition = [](BWAPI::Unit a, BWAPI::Unit b) {
            const auto pa = a->getPosition(), pb = b->getPosition();
            return std::tie(pa.y, pa.x) < std::tie(pb.y, pb.x);
        };
        std::sort(marines.begin(), marines.end(), byPosition);
        std::sort(zerglings.begin(), zerglings.end(), byPosition);
        for (size_t i = 0; i < marines.size(); ++i) {
            internalToCanonical_[marines[i]->getID()] = 1000 + static_cast<int>(i);
            canonicalToUnit_[1000 + static_cast<int>(i)] = marines[i];
        }
        for (size_t i = 0; i < zerglings.size(); ++i) {
            internalToCanonical_[zerglings[i]->getID()] = 2000 + static_cast<int>(i);
            canonicalToUnit_[2000 + static_cast<int>(i)] = zerglings[i];
        }
        internalToCanonical_[targets[0]->getID()] = 3000;
        canonicalToUnit_[3000] = targets[0];
        canonicalReady_ = true;
        std::cerr << "[frontier] canonical-units ready marines=4 zerglings=8 proxy=3000" << std::endl;
    }

    void logCombatDigest(BWAPI::Game* game, int frame) {
        if (!frontier_ || !canonicalReady_ || frame % 24 != 0) return;
        std::map<int, BWAPI::Unit> sorted;
        for (auto unit : game->getAllUnits()) {
            if (unit && (unit->getType() == BWAPI::UnitTypes::Terran_Marine
                         || unit->getType() == BWAPI::UnitTypes::Zerg_Zergling
                         || unit->getType() == BWAPI::UnitTypes::Terran_Missile_Turret))
                sorted[canonicalId(unit->getID())] = unit;
        }
        uint64_t hash = 1469598103934665603ull;
        std::ostringstream states;
        for (const auto& [id, unit] : sorted) {
            const int values[] = { id, unit->getPlayer()->getID(), unit->getType().getID(),
                unit->getPosition().x, unit->getPosition().y, unit->getHitPoints() };
            for (int value : values) {
                hash ^= static_cast<uint32_t>(value);
                hash *= 1099511628211ull;
            }
            if (states.tellp() > 0) states << ';';
            states << id << ',' << unit->getPosition().x << ',' << unit->getPosition().y
                   << ',' << unit->getHitPoints();
        }
        std::cerr << "[frontier] state-digest frame=" << frame << " hash=" << std::hex << hash
                  << std::dec << " units=" << sorted.size() << " state=" << states.str() << std::endl;
    }

    void executeMarineOrder(BWAPI::Game* game, const std::string& line) {
        static const std::regex format(
            R"(^order ([0-9a-f]{32}) ([0-9]{1,10}) ([0-9]{1,10}) (move|attack|hold) ([0-9]{1,5}) ([0-9]{1,5})$)");
        std::smatch match;
        if (!std::regex_match(line, match, format)) {
            std::cerr << "[frontier] rejected malformed command" << std::endl;
            return;
        }
        const std::string session = match[1];
        const std::string request = match[2];
        const int unitId = std::stoi(match[3]);
        const std::string action = match[4];
        const int x = std::stoi(match[5]);
        const int y = std::stoi(match[6]);
        BWAPI::Unit marine = canonicalToUnit_.count(unitId) ? canonicalToUnit_.at(unitId) : nullptr;
        BWAPI::Unit target = canonicalToUnit_.count(x) ? canonicalToUnit_.at(x) : nullptr;
        bool accepted = false;
        std::string reason = "invalid_marine";
        if (marine && marine->exists() && marine->getPlayer() == game->self()
            && marine->getType() == BWAPI::UnitTypes::Terran_Marine) {
            if (action == "hold" && x == 0 && y == 0) {
                accepted = marine->holdPosition();
                reason = accepted ? "ok" : "bwapi_rejected";
            } else if (action == "move" && x >= 0 && y >= 0
                       && x < game->mapWidth() * 32 && y < game->mapHeight() * 32) {
                accepted = marine->move({ x, y });
                reason = accepted ? "ok" : "bwapi_rejected";
            } else if (action == "attack" && y == 0 && target && target->exists()
                       && target->getPlayer() != game->self()
                       && target->getType() == BWAPI::UnitTypes::Zerg_Zergling) {
                accepted = marine->attack(target);
                reason = accepted ? "ok" : "bwapi_rejected";
            } else reason = "invalid_target";
        }
        if (!accepted && reason == "bwapi_rejected")
            std::cerr << "[frontier] BWAPI rejected command error=" << game->getLastError().toString() << std::endl;
        std::ostringstream reply;
        reply << "ack " << session << ' ' << request << ' ' << (accepted ? "accepted" : "rejected")
              << ' ' << reason;
        publisher_.publish(reply.str());
        std::cerr << "[frontier] order request=" << request << " marine=" << unitId
                  << " action=" << action << " accepted=" << accepted << " reason=" << reason << std::endl;
    }

    void startSiege(BWAPI::Game* game, BWAPI::Position spawn, BWAPI::Position target) {
        auto self = game->self();
        auto enemy = game->enemy();
        if (!enemy) {
            for (auto player : game->getPlayers()) {
                if (player && player != self && player->getRace() == BWAPI::Races::Terran &&
                    player->getType().toString() == "Player") {
                    enemy = player;
                    break;
                }
            }
        }
        if (!self || !enemy || self == enemy || self->getRace() != BWAPI::Races::Zerg ||
            enemy->getRace() != BWAPI::Races::Terran) {
            std::cerr << "[siege] invalid opposing Zerg/Terran players" << std::endl;
            return;
        }
        if (!self->isEnemy(enemy)) game->setAlliance(enemy, false, false);
        std::cerr << "[siege] players self=" << self->getID() << " enemy=" << enemy->getID()
                  << " game_type=" << game->getGameType().toString() << std::endl;
        std::cerr << "[siege] hostility zerg_to_terran=" << self->isEnemy(enemy)
                  << " terran_to_zerg=" << enemy->isEnemy(self) << std::endl;
        for (auto unit : game->getAllUnits()) {
            if (unit && unit->getPlayer() == enemy && unit->getType() == BWAPI::UnitTypes::Terran_Missile_Turret) {
                if (siegeTarget_) {
                    std::cerr << "[siege] multiple proxy structures in map" << std::endl;
                    return;
                }
                siegeTarget_ = unit;
            }
        }
        if (!siegeTarget_) {
            std::cerr << "[siege] missing preplaced Missile Turret" << std::endl;
            return;
        }
        const auto placed = siegeTarget_->getPosition();
        if (std::abs(placed.x - target.x) > 32 || std::abs(placed.y - target.y) > 32) {
            std::cerr << "[siege] proxy position does not match configured target" << std::endl;
            siegeTarget_ = nullptr;
            return;
        }
        siegeTargetId_ = siegeTarget_->getID();
        siegeInitialHp_ = siegeTarget_->getHitPoints();
        siegeLastHp_ = siegeInitialHp_;
        std::cerr << "[siege] target-created id=" << siegeTargetId_ << " owner=" << enemy->getID()
                  << " kind=Terran_Missile_Turret hp=" << siegeInitialHp_
                  << " max_hp=" << siegeTarget_->getType().maxHitPoints()
                  << " x=" << placed.x << " y=" << placed.y << std::endl;
        std::cerr << "[siege] attack orders scheduled for BW frame " << siegeStartFrame_ << std::endl;
        for (auto unit : game->getAllUnits()) {
            if (unit && unit->getPlayer() == self && unit->getType() == BWAPI::UnitTypes::Zerg_Zergling) {
                siegeUnits_.emplace(unit->getID(), BattleUnit{ unit, self->getID(), "zerg_zergling" });
                const auto pos = unit->getPosition();
                std::cerr << "[siege] zergling-created id=" << unit->getID() << " owner=" << self->getID()
                          << " x=" << pos.x << " y=" << pos.y << std::endl;
            }
        }
        if (siegeUnits_.size() != 8) std::cerr << "[siege] expected eight Zerglings, got " << siegeUnits_.size() << std::endl;
    }

    void siegeFrame(BWAPI::Game* game, int frame) {
        if (siegeTarget_ && siegeTarget_->exists() && siegeTarget_->getID() >= 0 && siegeTargetId_ < 0) {
            siegeTargetId_ = siegeTarget_->getID();
            siegeInitialHp_ = siegeTarget_->getHitPoints();
            siegeLastHp_ = siegeInitialHp_;
            std::cerr << "[siege] target-registered id=" << siegeTargetId_ << " hp=" << siegeInitialHp_ << std::endl;
        }
        if (siegeTarget_ && siegeTarget_->exists()) {
            const int hp = siegeTarget_->getHitPoints();
            if (siegeLastHp_ >= 0 && hp < siegeLastHp_) {
                std::cerr << "[siege] target-damage id=" << siegeTarget_->getID()
                          << " from=" << siegeLastHp_ << " to=" << hp << " frame=" << frame << std::endl;
            }
            siegeLastHp_ = hp;
        } else if (siegeTarget_ && !siegeDestroyed_ && siegeTargetId_ >= 0) {
            siegeDestroyed_ = true;
            siegeDestroyFrame_ = frame;
            std::cerr << "[siege] target-destroyed-fallback id=" << siegeTargetId_
                      << " frame=" << frame << std::endl;
        }
        for (auto& [id, tracked] : siegeUnits_) {
            auto unit = tracked.unit;
            if (!unit || !unit->exists()) continue;
            if (!tracked.ordered && frame >= siegeStartFrame_ && siegeTarget_ && siegeTarget_->exists()) {
                tracked.ordered = unit->attack(siegeTarget_);
                std::cerr << "[siege] attack-order id=" << id << " target=" << siegeTargetId_
                          << " accepted=" << tracked.ordered
                          << " error=" << game->getLastError().toString() << " frame=" << frame << std::endl;
            }
            const bool attackFrame = unit->isAttackFrame();
            if (attackFrame && !tracked.lastAttackFrame) {
                std::cerr << "[siege] attack-frame id=" << id << " target=" << siegeTargetId_
                          << " frame=" << frame << std::endl;
            }
            tracked.lastAttackFrame = attackFrame;
            if (frame % 24 == 0) {
                const auto position = unit->getPosition();
                std::cerr << "[siege] zergling-state id=" << id << " frame=" << frame
                          << " x=" << position.x << " y=" << position.y
                          << " order=" << unit->getOrder().toString() << std::endl;
            }
        }
        if (frame % 3 == 0 && frame != lastPublishedFrame_) {
            publishSiege(frame);
            lastPublishedFrame_ = frame;
        }
    }

    void publishSiege(int frame) {
        if (siegeTargetId_ < 0 || siegeUnits_.size() != 8) return;
        const int hp = siegeDestroyed_ || !siegeTarget_ || !siegeTarget_->exists()
            ? 0 : siegeTarget_->getHitPoints();
        const char* state = hp == 0 ? "destroyed" : hp < siegeInitialHp_ ? "damaged" : "intact";
        std::ostringstream line;
        line << "{\"v\":2,\"kind\":\"scenario.snapshot\",\"session\":\"" << session_
             << "\",\"map_id\":\"" << mapId_ << "\",\"seq\":" << ++sequence_
             << ",\"bw_tick\":" << frame << ",\"units\":[";
        size_t count = 0;
        for (const auto& [id, tracked] : siegeUnits_) {
            const auto unit = tracked.unit;
            if (!unit || !unit->exists()) continue;
            const auto pos = unit->getPosition();
            const bool moving = unit->isMoving()
                && std::hypot(unit->getVelocityX(), unit->getVelocityY()) >= 0.25;
            if (count++) line << ',';
            line << "{\"id\":\"openbw:" << id << "\",\"kind\":\"alien_scout\",\"x\":"
                 << pos.x << ",\"y\":" << pos.y << ",\"facing\":" << facingByte(unit->getAngle())
                 << ",\"motion\":\"" << (moving ? "walk" : "idle") << "\",\"alive\":true}";
        }
        line << "],\"targets\":[{\"id\":\"carousel-1\",\"proxy_unit_id\":\"openbw:"
             << siegeTargetId_ << "\",\"hp\":" << hp << ",\"max_hp\":" << siegeInitialHp_
             << ",\"state\":\"" << state << "\"}]}";
        publisher_.publish(line.str());
    }

    struct BattleUnit {
        BWAPI::Unit unit = nullptr;
        int owner = -1;
        std::string kind;
        int lastHp = -1;
        bool alive = true;
        bool ordered = false;
        bool lastAttackFrame = false;
        bool lastAttacking = false;
        int x = 0;
        int y = 0;
        int facing = 0;
        int deathFrame = -1;
        int attackFrames = 0;
    };

    void queueCombatEvent(const char* kind, int id, int value, int frame) {
        id = canonicalId(id);
        std::ostringstream event;
        event << "{\"id\":\"" << session_ << ':' << frame << ':' << kind << ':' << id
              << "\",\"kind\":\"" << kind << "\",\"unit_id\":\"openbw:" << id
              << "\",\"value\":" << value << ",\"bw_tick\":" << frame << '}';
        if (combatEvents_.size() < 64) combatEvents_.push_back(event.str());
    }

    void startFrontier(BWAPI::Game* game) {
        battleUnits_.clear();
        siegeTarget_ = nullptr;
        siegeTargetId_ = -1;
        auto self = game->self();
        auto enemy = game->enemy();
        std::cerr << "[frontier] probe self=" << (self ? self->getID() : -1)
                  << " race=" << (self ? self->getRace().toString() : "none")
                  << " enemy=" << (enemy ? enemy->getID() : -1)
                  << " race=" << (enemy ? enemy->getRace().toString() : "none")
                  << " game_type=" << game->getGameType().toString()
                  << " units=" << game->getAllUnits().size() << std::endl;
        if (!self || !enemy || self->getRace() != BWAPI::Races::Zerg ||
            enemy->getRace() != BWAPI::Races::Terran || !self->isEnemy(enemy) || !enemy->isEnemy(self)) {
            std::cerr << "[frontier] invalid opposing Zerg/Terran players" << std::endl;
            return;
        }
        battleTerranOwner_ = enemy->getID();
        for (auto unit : game->getAllUnits()) {
            if (!unit) continue;
            const auto type = unit->getType();
            if (unit->getPlayer() == enemy && type == BWAPI::UnitTypes::Terran_Missile_Turret) {
                if (siegeTarget_) { std::cerr << "[frontier] duplicate carousel proxy" << std::endl; return; }
                siegeTarget_ = unit;
                siegeTargetId_ = unit->getID();
                siegeInitialHp_ = unit->getHitPoints();
                siegeLastHp_ = siegeInitialHp_;
            } else if ((unit->getPlayer() == enemy && type == BWAPI::UnitTypes::Terran_Marine) ||
                       (unit->getPlayer() == self && type == BWAPI::UnitTypes::Zerg_Zergling)) {
                BattleUnit tracked{ unit, unit->getPlayer()->getID(),
                    type == BWAPI::UnitTypes::Terran_Marine ? "terran_marine" : "zerg_zergling" };
                tracked.x = unit->getPosition().x;
                tracked.y = unit->getPosition().y;
                battleUnits_.emplace(unit->getID(), tracked);
            }
        }
        const int marines = std::count_if(battleUnits_.begin(), battleUnits_.end(), [](const auto& entry) {
            return entry.second.kind == "terran_marine";
        });
        const int zerglings = static_cast<int>(battleUnits_.size()) - marines;
        std::cerr << "[frontier] spawned marines=" << marines << " zerglings=" << zerglings
                  << " proxy=" << siegeTargetId_ << " hp=" << siegeInitialHp_ << std::endl;
        if (marines != 4 || zerglings != 8 || siegeTargetId_ < 0 || siegeInitialHp_ != 200) {
            if (game->getFrameCount() >= 12)
                std::cerr << "[frontier] waiting for complete map fixture" << std::endl;
            battleUnits_.clear();
            return;
        }
        battleTarget_ = siegeTarget_->getPosition();
        frontierReady_ = true;
    }

    void startBattle(BWAPI::Game* game, BWAPI::Position zerg, BWAPI::Position terran) {
        auto self = game->self();
        auto enemy = game->enemy();
        std::cerr << "[battle] player probe self=" << (self ? self->getID() : -1)
                  << " race=" << (self ? self->getRace().toString() : "none")
                  << " enemy=" << (enemy ? enemy->getID() : -1)
                  << " race=" << (enemy ? enemy->getRace().toString() : "none")
                  << " self_enemy=" << (self && enemy ? self->isEnemy(enemy) : false)
                  << " enemy_self=" << (self && enemy ? enemy->isEnemy(self) : false) << std::endl;
        for (auto player : game->getPlayers()) {
            std::cerr << "[battle] player id=" << player->getID() << " race=" << player->getRace().toString()
                      << " type=" << player->getType().toString()
                      << " neutral=" << player->isNeutral() << " observer=" << player->isObserver()
                      << " enemy_of_self=" << (self ? self->isEnemy(player) : false) << std::endl;
        }
        if (!enemy) {
            for (auto player : game->getPlayers()) {
                if (player && player != self && player->getRace() == BWAPI::Races::Terran &&
                    player->getType().toString() == "Player") {
                    enemy = player;
                    break;
                }
            }
        }
        if (!self || !enemy || self == enemy || self->getRace() != BWAPI::Races::Zerg ||
            enemy->getRace() != BWAPI::Races::Terran) {
            std::cerr << "[battle] invalid opposing Zerg/Terran players" << std::endl;
            return;
        }
        battleTerranOwner_ = enemy->getID();
        logHostility(game, 0, "before-alliance-command");
        if (!self->isEnemy(enemy)) {
            const bool accepted = game->setAlliance(enemy, false, false);
            std::cerr << "[battle] setAlliance enemy accepted=" << accepted << std::endl;
        }
        std::cerr << "[battle] players zerg=" << self->getID() << " race=" << self->getRace().toString()
                  << " type=" << self->getType().toString() << " terran=" << enemy->getID()
                  << " race=" << enemy->getRace().toString() << " type=" << enemy->getType().toString() << std::endl;
        logHostility(game, 0, "initial");
        battleTarget_ = terran;
        for (int index = 0; index < 4; ++index) {
            BWAPI::Position pos{ terran.x + (index % 2) * 24, terran.y + (index / 2) * 24 };
            addBattleUnit(game, enemy, BWAPI::UnitTypes::Terran_Marine, pos, "terran_marine");
        }
        for (int index = 0; index < 8; ++index) {
            BWAPI::Position pos{ zerg.x + (index % 2) * 24, zerg.y + (index / 2) * 24 };
            addBattleUnit(game, self, BWAPI::UnitTypes::Zerg_Zergling, pos, "zerg_zergling");
        }
        std::cerr << "[battle] scenario started candidates=" << battlePending_.size() << std::endl;
    }

    void addBattleUnit(BWAPI::Game* game, BWAPI::Player owner, BWAPI::UnitType type,
                       BWAPI::Position pos, const char* kind) {
        auto unit = game->createUnit(owner, type, pos);
        if (!unit) {
            std::cerr << "[battle] createUnit failed kind=" << kind << " owner=" << owner->getID()
                      << " error=" << game->getLastError().toString() << std::endl;
            return;
        }
        const int id = unit->getID();
        battlePending_.push_back(BattleUnit{ unit, owner->getID(), kind });
        std::cerr << "[battle] created candidate_id=" << id << " owner=" << owner->getID() << " kind=" << kind
                  << " x=" << pos.x << " y=" << pos.y << std::endl;
    }

    void battleFrame(BWAPI::Game* game, int frame) {
        for (auto it = battlePending_.begin(); it != battlePending_.end();) {
            if (it->unit && it->unit->exists() && it->unit->getID() >= 0) {
                const int id = it->unit->getID();
                std::cerr << "[battle] registered id=" << id << " owner=" << it->owner
                          << " kind=" << it->kind << std::endl;
                battleUnits_.emplace(id, *it);
                it = battlePending_.erase(it);
            } else {
                ++it;
            }
        }
        if (!battleSpawnLogged_ && battlePending_.empty()) {
            battleSpawnLogged_ = true;
            int marines = 0, zerglings = 0;
            for (const auto& [id, unit] : battleUnits_) {
                if (unit.kind == "terran_marine") ++marines;
                else if (unit.kind == "zerg_zergling") ++zerglings;
            }
            std::cerr << "[battle] spawned marines=" << marines << " zerglings=" << zerglings << std::endl;
        }
        if (frame == 6) logHostility(game, frame, "orders");
        int zergAlive = 0, terranAlive = 0;
        int nearestDistanceSquared = 1000000000;
        for (auto& [id, tracked] : battleUnits_) {
            auto unit = tracked.unit;
            if (!unit || !unit->exists()) {
                if (tracked.alive) {
                    tracked.alive = false;
                    tracked.deathFrame = frame;
                    queueCombatEvent("death", id, 0, frame);
                    std::cerr << "[battle] destroyed-fallback id=" << id << " owner=" << tracked.owner
                              << " kind=" << tracked.kind << " frame=" << frame << std::endl;
                }
                continue;
            }
            if (tracked.kind == "zerg_zergling") {
                ++zergAlive;
                if (!tracked.ordered && frame >= (frontier_ ? siegeStartFrame_ : 6)) {
                    tracked.ordered = unit->attack(battleTarget_);
                    std::cerr << "[battle] attack-move id=" << id << " accepted=" << tracked.ordered
                              << " target=" << battleTarget_.x << "," << battleTarget_.y
                              << " error=" << game->getLastError().toString() << std::endl;
                }
                if (frontier_ && siegeTarget_ && siegeTarget_->exists() && frame >= 24
                    && (unit->getPosition().getApproxDistance(siegeTarget_->getPosition()) < 80)
                    && unit->getOrderTarget() != siegeTarget_ && !unit->isAttacking()) {
                    const bool accepted = unit->attack(siegeTarget_);
                    if (accepted) std::cerr << "[frontier] proxy-attack id=" << id << " target=" << siegeTargetId_ << std::endl;
                }
            } else {
                ++terranAlive;
                if (probeEnemyOrders_ && frame >= 12 && !tracked.ordered) {
                    tracked.ordered = true;
                    const bool accepted = unit->attack(BWAPI::Position{ 320, 480 });
                    std::cerr << "[battle] enemy-marine-attack-probe id=" << id << " accepted=" << accepted
                              << " error=" << game->getLastError().toString() << std::endl;
                }
            }
            const int hp = unit->getHitPoints();
            if (tracked.lastHp >= 0 && hp < tracked.lastHp) {
                queueCombatEvent("damage", id, tracked.lastHp - hp, frame);
                if (!battleDamageObserved_) {
                    battleDamageObserved_ = true;
                    logHostility(game, frame, "after-contact");
                }
                std::cerr << "[battle] damage id=" << id << " owner=" << tracked.owner << " kind=" << tracked.kind
                          << " from=" << tracked.lastHp << " to=" << hp << " frame=" << frame << std::endl;
            }
            tracked.lastHp = hp;
            const bool attackFrame = unit->isAttackFrame();
            const bool attacking = unit->isAttacking();
            if (attackFrame && !tracked.lastAttackFrame) {
                ++tracked.attackFrames;
                queueCombatEvent("attack_frame", id, tracked.attackFrames, frame);
                auto target = unit->getTarget();
                auto orderTarget = unit->getOrderTarget();
                std::cerr << "[battle] attack-frame frame=" << frame << " id=" << id << " owner=" << tracked.owner
                          << " kind=" << tracked.kind << " hp=" << hp << " cooldown="
                          << unit->getGroundWeaponCooldown() << " target=" << (target ? target->getID() : -1)
                          << " orderTarget=" << (orderTarget ? orderTarget->getID() : -1)
                          << " order=" << unit->getOrder().toString() << std::endl;
            }
            if (attacking && !tracked.lastAttacking) {
                auto target = unit->getTarget();
                std::cerr << "[battle] attack-start frame=" << frame << " id=" << id << " owner=" << tracked.owner
                          << " kind=" << tracked.kind << " target=" << (target ? target->getID() : -1) << std::endl;
            }
            tracked.lastAttackFrame = attackFrame;
            tracked.lastAttacking = attacking;
            tracked.x = unit->getPosition().x;
            tracked.y = unit->getPosition().y;
            tracked.facing = facingByte(unit->getAngle());
            if (traceBattle_ || frame % 24 == 0) {
                const auto pos = unit->getPosition();
                auto target = unit->getTarget();
                auto orderTarget = unit->getOrderTarget();
                std::cerr << "[battle] state frame=" << frame << " id=" << id << " owner=" << tracked.owner
                          << " kind=" << tracked.kind << " hp=" << hp << " max_hp=" << unit->getType().maxHitPoints()
                          << " order=" << unit->getOrder().toString() << " cooldown=" << unit->getGroundWeaponCooldown()
                          << " target=" << (target ? target->getID() : -1)
                          << " orderTarget=" << (orderTarget ? orderTarget->getID() : -1)
                          << " attacking=" << attacking << " attackFrame=" << attackFrame
                          << " facing=" << facingByte(unit->getAngle())
                          << " x=" << pos.x << " y=" << pos.y << std::endl;
            }
        }
        if (!battleBeforeContactLogged_ && zergAlive && terranAlive) {
            for (const auto& [zergId, zerg] : battleUnits_) {
                if (!zerg.alive || zerg.kind != "zerg_zergling" || !zerg.unit || !zerg.unit->exists()) continue;
                for (const auto& [terranId, terran] : battleUnits_) {
                    if (!terran.alive || terran.kind != "terran_marine" || !terran.unit || !terran.unit->exists()) continue;
                    const auto a = zerg.unit->getPosition(), b = terran.unit->getPosition();
                    const int dx = a.x - b.x, dy = a.y - b.y;
                    nearestDistanceSquared = std::min(nearestDistanceSquared, dx * dx + dy * dy);
                }
            }
            if (nearestDistanceSquared <= 192 * 192) {
                battleBeforeContactLogged_ = true;
                logHostility(game, frame, "before-contact");
            }
        }
        if (!battleComplete_ && frame >= 24 && battlePending_.empty() &&
            (!zergAlive || !terranAlive || frame >= environmentInteger("BRIDGE_BATTLE_TIMEOUT_FRAMES", 1800))) {
            battleComplete_ = true;
            std::cerr << "[battle] outcome frame=" << frame << " zerg_alive=" << zergAlive
                      << " terran_alive=" << terranAlive << " result="
                      << (!zergAlive ? "terran" : !terranAlive ? "zerg" : "timeout") << std::endl;
        }
        if (frontier_ && siegeTargetId_ >= 0) {
            const int hp = siegeTarget_ && siegeTarget_->exists() ? siegeTarget_->getHitPoints() : 0;
            if (siegeLastHp_ >= 0 && hp < siegeLastHp_)
            {
                std::cerr << "[frontier] target-damage id=" << siegeTargetId_ << " from=" << siegeLastHp_
                          << " to=" << hp << " frame=" << frame << std::endl;
                queueCombatEvent("damage", siegeTargetId_, siegeLastHp_ - hp, frame);
            }
            siegeLastHp_ = hp;
            if (hp == 0 && !siegeDestroyed_) {
                siegeDestroyed_ = true;
                queueCombatEvent("destruction", siegeTargetId_, 0, frame);
            }
        }
        if ((battle_ || frontier_) && frame % 3 == 0 && frame != lastPublishedFrame_) {
            publishCombat(frame);
            lastPublishedFrame_ = frame;
        }
    }

    void publishCombat(int frame) {
        if (battleUnits_.size() != 12) return;
        std::ostringstream line;
        line << "{\"v\":3,\"kind\":\"scenario.snapshot\",\"session\":\"" << session_
             << "\",\"map_id\":\"" << mapId_ << "\",\"seq\":" << ++sequence_
             << ",\"bw_tick\":" << frame << ",\"units\":[";
        size_t count = 0;
        for (const auto& [id, tracked] : battleUnits_) {
            const auto unit = tracked.unit;
            const bool alive = tracked.alive && unit && unit->exists();
            if (!alive && (tracked.deathFrame < 0 || frame - tracked.deathFrame > 16)) continue;
            if (count++) line << ',';
            const int x = alive ? unit->getPosition().x : tracked.x;
            const int y = alive ? unit->getPosition().y : tracked.y;
            const int facing = alive ? facingByte(unit->getAngle()) : tracked.facing;
            const int hp = alive ? unit->getHitPoints() : 0;
            const bool moving = alive && unit->isMoving()
                && std::hypot(unit->getVelocityX(), unit->getVelocityY()) >= 0.25;
            const char* motion = !alive ? "death" : unit->isAttacking() ? "attack" : moving ? "walk" : "idle";
            const auto target = alive ? unit->getTarget() : nullptr;
            line << "{\"id\":\"openbw:" << canonicalId(id) << "\",\"kind\":\"" << tracked.kind
                 << "\",\"owner\":" << tracked.owner << ",\"x\":" << x << ",\"y\":" << y
                 << ",\"facing\":" << facing << ",\"motion\":\"" << motion
                 << "\",\"hp\":" << hp << ",\"max_hp\":"
                 << (tracked.kind == "terran_marine" ? 40 : 35)
                 << ",\"alive\":" << (alive ? "true" : "false")
                 << ",\"attack_frames\":" << tracked.attackFrames << ",\"target_id\":";
            if (target) line << "\"openbw:" << canonicalId(target->getID()) << "\"";
            else line << "null";
            line << '}';
        }
        line << "],\"targets\":[";
        if (frontier_) {
            const int hp = siegeTarget_ && siegeTarget_->exists() ? siegeTarget_->getHitPoints() : 0;
            line << "{\"id\":\"carousel-1\",\"proxy_unit_id\":\"openbw:" << canonicalId(siegeTargetId_)
                 << "\",\"hp\":" << hp << ",\"max_hp\":" << siegeInitialHp_
                 << ",\"state\":\"" << (hp == 0 ? "destroyed" : hp < siegeInitialHp_ ? "damaged" : "intact") << "\"}";
        }
        line << "],\"events\":[";
        for (size_t index = 0; index < combatEvents_.size(); ++index) {
            if (index) line << ',';
            line << combatEvents_[index];
        }
        line << "]}";
        publisher_.publish(line.str());
        combatEvents_.clear();
    }

    void logHostility(BWAPI::Game* game, int frame, const char* phase) {
        auto self = game->self();
        auto enemy = game->getPlayer(battleTerranOwner_);
        std::cerr << "[battle] hostility frame=" << frame << " phase=" << phase
                  << " zerg_to_terran=" << (self && enemy ? self->isEnemy(enemy) : false)
                  << " terran_to_zerg=" << (self && enemy ? enemy->isEnemy(self) : false)
                  << " zerg_ally=" << (self && enemy ? self->isAlly(enemy) : false)
                  << " terran_ally=" << (self && enemy ? enemy->isAlly(self) : false) << std::endl;
    }

    struct PatrolUnit {
        BWAPI::Unit unit = nullptr;
        BWAPI::Position spawn;
        BWAPI::Position outbound;
        BWAPI::Position target;
        bool returning = false;
        bool initialMoveAccepted = false;
        int lastMoveAttemptFrame = -24;
        int lastCorrectionFrame = -24;
    };

    struct PendingUnit {
        BWAPI::Unit unit;
        BWAPI::Position spawn;
        BWAPI::Position outbound;
    };

    void registerPending(BWAPI::Game* game) {
        for (auto it = pending_.begin(); it != pending_.end();) {
            if (it->unit && it->unit->exists() && it->unit->getID() >= 0 && it->unit->getPlayer() == game->self()) {
                const int id = it->unit->getID();
                units_.emplace(id, PatrolUnit{ it->unit, it->spawn, it->outbound, it->outbound });
                std::cerr << "[bridge] registered unit id=" << id << std::endl;
                it = pending_.erase(it);
            } else {
                ++it;
            }
        }
    }

    bool orderMove(int id, PatrolUnit& patrol, BWAPI::Position destination) {
        if (!patrol.unit || !patrol.unit->move(destination)) {
            std::cerr << "[bridge] Unit::move failed: " << BWAPI::Broodwar->getLastError().toString() << std::endl;
            return false;
        } else {
            std::cerr << "[bridge] Unit::move id=" << id << " target=" << destination.x << "," << destination.y << std::endl;
            return true;
        }
    }

    void publish(int frame) {
        std::ostringstream line;
        line << "{\"v\":1,\"kind\":\"units.snapshot\",\"session\":\"" << session_
             << "\",\"map_id\":\"" << mapId_ << "\",\"seq\":" << ++sequence_
             << ",\"bw_tick\":" << frame << ",\"units\":[";
        size_t count = 0;
        for (const auto& [id, patrol] : units_) {
            auto unit = patrol.unit;
            if (!unit || !unit->exists() || count >= kMaxUnits) continue;
            const auto position = unit->getPosition();
            const int facing = facingByte(unit->getAngle());
            // BWAPI may keep isMoving() true for a move order to the current
            // position. Animation should follow actual motion, not the order.
            const bool moving = unit->isMoving()
                && std::hypot(unit->getVelocityX(), unit->getVelocityY()) >= 0.25;
            if (count++) line << ',';
            line << "{\"id\":\"openbw:" << id << "\",\"kind\":\"alien_scout\",\"x\":"
                 << position.x << ",\"y\":" << position.y << ",\"facing\":" << facing
                 << ",\"motion\":\"" << (moving ? "walk" : "idle") << "\",\"alive\":true}";
            std::cerr << "[bridge] tick=" << frame << " seq=" << sequence_ << " id=" << id
                      << " x=" << position.x << " y=" << position.y << " facing=" << facing
                      << " motion=" << (moving ? "walk" : "idle") << std::endl;
        }
        line << "]}";
        publisher_.publish(line.str());
    }

    LoopbackPublisher publisher_;
    std::map<int, BattleUnit> battleUnits_;
    std::map<int, BattleUnit> siegeUnits_;
    BWAPI::Unit siegeTarget_ = nullptr;
    int siegeTargetId_ = -1;
    int siegeInitialHp_ = -1;
    int siegeLastHp_ = -1;
    int siegeDestroyFrame_ = -1;
    bool siegeDestroyed_ = false;
    std::vector<BattleUnit> battlePending_;
    BWAPI::Position battleTarget_;
    int battleTerranOwner_ = -1;
    bool battle_ = false;
    bool frontier_ = false;
    bool frontierReady_ = false;
    bool canonicalReady_ = false;
    std::map<int, int> internalToCanonical_;
    std::map<int, BWAPI::Unit> canonicalToUnit_;
    bool terranController_ = false;
    std::vector<std::string> combatEvents_;
    bool siege_ = false;
    bool parkAssault_ = false;
    bool assaultNavReady_ = false;
    bool assaultReady_ = false;
    bool assaultStartWarning_ = false;
    ParkAssaultNavigation assaultNav_;
    std::map<std::string, AssaultTarget> assaultTargets_;
    std::map<int, AssaultUnit> assaultUnits_;
    bool probeEnemyOrders_ = false;
    bool traceBattle_ = false;
    bool battleComplete_ = false;
    bool battleBeforeContactLogged_ = false;
    bool battleDamageObserved_ = false;
    bool battleSpawnLogged_ = false;
    std::map<int, PatrolUnit> units_;
    std::vector<PendingUnit> pending_;
    int demoUnits_ = 1;
    uint64_t sequence_ = 0;
    int lastPublishedFrame_ = -1;
    int frameDelayMs_ = 42;
    int siegeStartFrame_ = 48;
    std::string session_;
    std::string mapId_;
};

}  // namespace

extern "C" void gameInit(BWAPI::Game* game) { BWAPI::BroodwarPtr = game; }
extern "C" BWAPI::AIModule* newAIModule() { return new BridgeAIModule(); }
