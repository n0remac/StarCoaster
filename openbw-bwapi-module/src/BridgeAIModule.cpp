#include <BWAPI.h>

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
#include <random>
#include <sstream>
#include <string>
#include <thread>

namespace {

constexpr double kTau = 6.28318530717958647692;

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
        spawn_ = BWAPI::Position(spawnX, spawnY);
        target_ = BWAPI::Position(targetX, targetY);
        unit_ = game->createUnit(game->self(), BWAPI::UnitTypes::Zerg_Zergling, spawn_);
        if (!unit_) {
            std::cerr << "[bridge] createUnit failed: " << game->getLastError().toString() << std::endl;
            return;
        }
        std::cerr << "[bridge] createUnit returned at " << spawnX << "," << spawnY
                  << "; waiting for BWAPI unit registration before ordering movement" << std::endl;
    }

    void onFrame() override {
        // The OpenBW launcher does not pace frames when its UI is disabled.
        // Pace its simulation loop here so every third-frame snapshot is about 8 Hz.
        if (frameDelayMs_ > 0) std::this_thread::sleep_for(std::chrono::milliseconds(frameDelayMs_));
        publisher_.poll();
        auto* game = BWAPI::Broodwar.operator->();
        if (!game) return;
        const int frame = game->getFrameCount();
        if (unit_ && unit_->exists() && unit_->getID() >= 0 && unit_->getPlayer() == game->self()) {
            if (unitId_ < 0) {
                unitId_ = unit_->getID();
                std::cerr << "[bridge] registered unit id=" << unitId_ << std::endl;
            }
            if (!initialMoveAccepted_) {
                if (frame - lastMoveAttemptFrame_ >= 24) {
                    lastMoveAttemptFrame_ = frame;
                    initialMoveAccepted_ = orderMove(target_);
                }
            } else {
                const auto current = unit_->getPosition();
                const int dx = current.x - target_.x;
                const int dy = current.y - target_.y;
                if (!unit_->isMoving() && dx * dx + dy * dy <= 16 * 16) {
                    target_ = returning_ ? BWAPI::Position(environmentInteger("BRIDGE_TARGET_X", 640),
                                                            environmentInteger("BRIDGE_TARGET_Y", 480)) : spawn_;
                    returning_ = !returning_;
                    orderMove(target_);
                }
            }
        }
        if (frame % 3 == 0 && frame != lastPublishedFrame_) {
            publish(frame);
            lastPublishedFrame_ = frame;
        }
    }

    void onUnitDestroy(BWAPI::Unit unit) override {
        if (unit && unit->getID() == unitId_) {
            unit_ = nullptr;
            std::cerr << "[bridge] unit destroyed id=" << unitId_ << std::endl;
            publish(BWAPI::Broodwar->getFrameCount());
        }
    }

    void onEnd(bool) override {
        unit_ = nullptr;
        publish(BWAPI::Broodwar->getFrameCount());
    }

private:
    bool orderMove(BWAPI::Position destination) {
        if (!unit_ || !unit_->move(destination)) {
            std::cerr << "[bridge] Unit::move failed: " << BWAPI::Broodwar->getLastError().toString() << std::endl;
            return false;
        } else {
            std::cerr << "[bridge] Unit::move id=" << unitId_ << " target=" << destination.x << "," << destination.y << std::endl;
            return true;
        }
    }

    void publish(int frame) {
        std::ostringstream line;
        line << "{\"v\":1,\"kind\":\"units.snapshot\",\"session\":\"" << session_
             << "\",\"map_id\":\"" << mapId_ << "\",\"seq\":" << ++sequence_
             << ",\"bw_tick\":" << frame << ",\"units\":[";
        if (unit_ && unit_->exists() && unitId_ >= 0) {
            const auto position = unit_->getPosition();
            const int facing = facingByte(unit_->getAngle());
            // BWAPI may keep isMoving() true for a move order to the current
            // position. Animation should follow actual motion, not the order.
            const bool moving = unit_->isMoving()
                && std::hypot(unit_->getVelocityX(), unit_->getVelocityY()) >= 0.25;
            line << "{\"id\":\"openbw:" << unitId_ << "\",\"kind\":\"alien_scout\",\"x\":"
                 << position.x << ",\"y\":" << position.y << ",\"facing\":" << facing
                 << ",\"motion\":\"" << (moving ? "walk" : "idle") << "\",\"alive\":true}";
            std::cerr << "[bridge] tick=" << frame << " seq=" << sequence_ << " id=" << unitId_
                      << " x=" << position.x << " y=" << position.y << " moving=" << moving << std::endl;
        }
        line << "]}";
        publisher_.publish(line.str());
    }

    LoopbackPublisher publisher_;
    BWAPI::Unit unit_ = nullptr;
    int unitId_ = -1;
    BWAPI::Position spawn_;
    BWAPI::Position target_;
    bool returning_ = false;
    uint64_t sequence_ = 0;
    int lastPublishedFrame_ = -1;
    int lastMoveAttemptFrame_ = -24;
    bool initialMoveAccepted_ = false;
    int frameDelayMs_ = 42;
    std::string session_;
    std::string mapId_;
};

}  // namespace

extern "C" void gameInit(BWAPI::Game* game) { BWAPI::BroodwarPtr = game; }
extern "C" BWAPI::AIModule* newAIModule() { return new BridgeAIModule(); }
