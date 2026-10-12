#pragma once

#include <BWAPI.h>
#include <nlohmann/json.hpp>
#include "WorldActorRegistry.h"

#include <arpa/inet.h>
#include <fcntl.h>
#include <sys/socket.h>
#include <unistd.h>

#include <cerrno>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <iostream>
#include <map>
#include <set>
#include <string>

// Runs in the Terran BWAPI player slot of the same OpenBW multiplayer game.
// Every command is applied in onFrame and BWAPI enforces player ownership.
class WorldUnitController {
    using json = nlohmann::json;
public:
    ~WorldUnitController() { closeSocket(); }
    void onFrame(BWAPI::Game* game) {
        actorRegistry_.prepare(game);
        if (socket_ < 0) connect(game);
        if (socket_ < 0) return;
        char bytes[8192];
        for (;;) {
            const ssize_t count = ::recv(socket_, bytes, sizeof(bytes), 0);
            if (count > 0) {
                incoming_.append(bytes, static_cast<size_t>(count));
                if (incoming_.size() > 1048576) { closeSocket(); return; }
            } else if (count == 0) { closeSocket(); return; }
            else if (errno == EAGAIN || errno == EWOULDBLOCK) break;
            else { closeSocket(); return; }
        }
        size_t newline;
        int processed = 0;
        while (processed++ < 32 && (newline = incoming_.find('\n')) != std::string::npos) {
            const auto line = incoming_.substr(0, newline);
            incoming_.erase(0, newline + 1);
            if (line.size() > 131072) { closeSocket(); return; }
            try { handle(game, json::parse(line)); }
            catch (const std::exception& error) {
                std::cerr << "[world-control] malformed message: " << error.what() << std::endl;
            }
        }
        flush();
    }
private:
    struct TargetLink { std::string proxyID; int x = 0, y = 0; };
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
        incoming_.clear(); outgoing_.clear(); session_.clear(); revision_ = 0;
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
              const json& payload) {
        json message = {{"v", 1}, {"kind", kind}, {"session", session},
            {"op_id", "controller:" + std::to_string(++sequence_)}, {"source", "openbw"},
            {"revision", revision}, {"payload", payload}};
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
        } else if (commandID.empty() || !units.is_array() || units.empty() || units.size() > 32
            || (verb != "unit.move" && verb != "unit.attack" && verb != "unit.attack_move"
                && verb != "unit.hold" && verb != "unit.stop")) {
            accepted = false; reason = "invalid_command";
        } else if (!validCommandSerial(commandID)) {
            accepted = false; reason = "duplicate_command";
        }
        BWAPI::Unit target = nullptr;
        if (accepted && verb == "unit.attack") {
            const auto targetID = command.value("target_id", "");
            if (targetID.compare(0, 7, "openbw:") == 0) target = actorRegistry_.lookup(targetID);
            else {
                const auto link = targetLinks_.find(targetID);
                if (link != targetLinks_.end()) {
                    bool ambiguousLink = false;
                    for (const auto& other : targetLinks_)
                        if (other.first != targetID &&
                            std::abs(other.second.x - link->second.x) <= 32 &&
                            std::abs(other.second.y - link->second.y) <= 32)
                            ambiguousLink = true;
                    int matches = 0;
                    for (auto candidate : game->getAllUnits()) {
                        if (!candidate || !candidate->exists()
                            || candidate->getType() != BWAPI::UnitTypes::Terran_Civilian
                            || candidate->getPlayer() == game->self()) continue;
                        const auto position = candidate->getPosition();
                        if (std::abs(position.x - link->second.x) <= 16
                            && std::abs(position.y - link->second.y) <= 16) {
                            target = candidate; ++matches;
                        }
                    }
                    if (matches != 1 || ambiguousLink) target = nullptr;
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
                || unit->getType() != BWAPI::UnitTypes::Terran_Marine) {
                accepted = false; reason = "invalid_owner_or_unit"; break;
            }
        }
        if (accepted) {
            revision_ = message.at("revision").get<uint64_t>();
            lastCommandSerial_ = std::stoull(commandID.substr(session_.size() + 1));
            for (const auto& idValue : units) {
                auto unit = actorRegistry_.lookup(idValue.get<std::string>());
                bool applied = false;
                if (verb == "unit.move") applied = unit->move({x, y});
                else if (verb == "unit.attack_move") applied = unit->attack({x, y});
                else if (verb == "unit.attack") applied = unit->attack(target);
                else if (verb == "unit.hold") applied = unit->holdPosition();
                else if (verb == "unit.stop") applied = unit->stop();
                if (!applied) { accepted = false; reason = "bwapi_rejected"; }
                std::cerr << "[world-control] command=" << commandID << " unit=" << unit->getID()
                          << " verb=" << verb << " accepted=" << applied
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
    WorldActorRegistry actorRegistry_;
};
