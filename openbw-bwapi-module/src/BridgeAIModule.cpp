#include <BWAPI.h>

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
#include <sstream>
#include <string>
#include <thread>
#include <vector>

namespace {

constexpr double kTau = 6.28318530717958647692;
constexpr size_t kMaxLine = 16384;
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
        traceBattle_ = std::getenv("BRIDGE_BATTLE_TRACE") != nullptr;
        probeEnemyOrders_ = std::getenv("BRIDGE_PROBE_ENEMY_ORDERS") != nullptr;
        const char* scenario = std::getenv("BRIDGE_SCENARIO");
        battle_ = scenario && std::strcmp(scenario, "battle") == 0;
        siege_ = scenario && std::strcmp(scenario, "ride_siege") == 0;
        if (scenario && *scenario && !battle_ && !siege_ && std::strcmp(scenario, "patrol") != 0) {
            std::cerr << "[bridge] unknown BRIDGE_SCENARIO=" << scenario << std::endl;
            return;
        }
        mapId_ = environmentMapId();
        session_ = newSessionId();
        std::cerr << "[bridge] session=" << session_ << std::endl;
        publisher_.start(port);

        auto* game = BWAPI::Broodwar.operator->();
        if (!game || game->isReplay() || !game->self()) {
            std::cerr << "[bridge] no active player; unit creation skipped" << std::endl;
            return;
        }
        const int maxX = game->mapWidth() * 32;
        const int maxY = game->mapHeight() * 32;
        if (spawnX >= maxX || spawnY >= maxY || targetX >= maxX || targetY >= maxY) {
            std::cerr << "[bridge] configured coordinates exceed map bounds " << maxX << "x" << maxY << std::endl;
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
        const int frame = game->getFrameCount();
        if (battle_) {
            battleFrame(game, frame);
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
        if (siege_) {
            if (unit && unit->getID() == siegeTargetId_) {
                siegeDestroyed_ = true;
                siegeDestroyFrame_ = BWAPI::Broodwar->getFrameCount();
                std::cerr << "[siege] target-destroyed id=" << siegeTargetId_
                          << " frame=" << siegeDestroyFrame_ << std::endl;
            }
            return;
        }
        if (battle_) {
            if (unit) {
                auto it = battleUnits_.find(unit->getID());
                if (it != battleUnits_.end()) {
                    std::cerr << "[battle] destroyed id=" << it->first << " owner=" << it->second.owner
                              << " kind=" << it->second.kind << " frame=" << BWAPI::Broodwar->getFrameCount() << std::endl;
                    it->second.alive = false;
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
        if (battle_ || siege_) return;
        units_.clear();
        pending_.clear();
        publish(BWAPI::Broodwar->getFrameCount());
    }

private:
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
            if (!tracked.ordered && frame >= 6 && siegeTarget_ && siegeTarget_->exists()) {
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
    };

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
                    std::cerr << "[battle] destroyed-fallback id=" << id << " owner=" << tracked.owner
                              << " kind=" << tracked.kind << " frame=" << frame << std::endl;
                }
                continue;
            }
            if (tracked.kind == "zerg_zergling") {
                ++zergAlive;
                if (!tracked.ordered && frame >= 6) {
                    tracked.ordered = unit->attack(battleTarget_);
                    std::cerr << "[battle] attack-move id=" << id << " accepted=" << tracked.ordered
                              << " target=" << battleTarget_.x << "," << battleTarget_.y
                              << " error=" << game->getLastError().toString() << std::endl;
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
    bool siege_ = false;
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
    std::string session_;
    std::string mapId_;
};

}  // namespace

extern "C" void gameInit(BWAPI::Game* game) { BWAPI::BroodwarPtr = game; }
extern "C" BWAPI::AIModule* newAIModule() { return new BridgeAIModule(); }
