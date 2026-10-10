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
        if (unit && units_.erase(unit->getID())) {
            std::cerr << "[bridge] unit destroyed id=" << unit->getID() << std::endl;
            publish(BWAPI::Broodwar->getFrameCount());
        }
    }

    void onEnd(bool) override {
        units_.clear();
        pending_.clear();
        publish(BWAPI::Broodwar->getFrameCount());
    }

private:
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
