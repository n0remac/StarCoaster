#pragma once

#include <nlohmann/json.hpp>

#include <cstdint>
#include <map>
#include <set>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace starcoaster {

using Json = nlohmann::json;

struct Rect {
    int x = 0, y = 0, width = 0, height = 0;
    bool operator==(const Rect& other) const {
        return x == other.x && y == other.y && width == other.width && height == other.height;
    }
};

struct Entity {
    std::string id, sourceId, kind;
    int health = 0, armor = 0;
    bool destructible = false, targetable = false, blocks = false;
    std::vector<Rect> rectangles;
    Json raw;
};

inline Entity parseEntity(const Json& value, int width, int height) {
    Entity e;
    e.id = value.at("id").get<std::string>();
    e.sourceId = value.at("source_id").get<std::string>();
    e.kind = value.at("kind").get<std::string>();
    e.destructible = value.at("destructible").get<bool>();
    e.targetable = value.at("combat").at("targetable").get<bool>();
    e.health = value.at("combat").at("health").get<int>();
    e.armor = value.at("combat").value("armor", 0);
    e.blocks = value.at("collision").at("blocks").get<bool>();
    if (e.id.empty() || e.id.size() > 256 || e.sourceId.empty() || e.kind.empty()
        || value.at("source") != "openrct2" || e.health < 0 || e.health > 100000
        || e.armor < 0 || e.armor > 255 || (e.targetable && !e.destructible))
        throw std::invalid_argument("invalid_entity_identity_or_combat");
    const auto rects = value.at("geometry").value("rects", Json::array());
    if (!rects.is_array() || rects.size() > 8192) throw std::invalid_argument("invalid_footprint_size");
    for (const auto& rectangle : rects) {
        Rect r{rectangle.at("x"), rectangle.at("y"), rectangle.at("width"), rectangle.at("height")};
        if (r.x < 0 || r.y < 0 || r.width < 1 || r.height < 1
            || static_cast<int64_t>(r.x) + r.width > static_cast<int64_t>(width) * 32
            || static_cast<int64_t>(r.y) + r.height > static_cast<int64_t>(height) * 32)
            throw std::invalid_argument("invalid_footprint_bounds");
        e.rectangles.push_back(r);
    }
    e.raw = value;
    return e;
}

struct DesiredWorld {
    std::string session;
    uint64_t revision = 0;
    int width = 0, height = 0;
    int terrainCount = 0;
    std::map<std::string, Entity> entities;
};

// This component performs all logical validation before the simulation is
// touched. A repeated snapshot can be applied safely after bridge recovery.
class SnapshotStager {
public:
    bool begin(const std::string& session, uint64_t revision, int width, int height,
               int chunks, const std::string& activeSession, uint64_t activeRevision,
               std::string& error) {
        if (session.empty() || session.size() > 128 || revision == 0 || width < 1 || height < 1
            || width > 1024 || height > 1024 || chunks < 1 || chunks > 100000) {
            error = "invalid_snapshot_begin"; return false;
        }
        if (session == activeSession && revision < activeRevision) {
            error = "stale_world"; return false;
        }
        desired_ = DesiredWorld{};
        desired_.session = session;
        desired_.revision = revision;
        desired_.width = width;
        desired_.height = height;
        expected_ = chunks;
        received_ = 0;
        seen_.clear();
        active_ = true;
        return true;
    }
    bool chunk(const std::string& operation, int index, const Json& entities,
               const Json& terrain, std::string& error) {
        if (!active_) { error = "no_snapshot"; return false; }
        if (seen_.count(operation)) return true;
        if (operation.empty() || index != received_ || received_ >= expected_ || !entities.is_array()
            || !terrain.is_array() || entities.size() > 64 || terrain.size() > 512) {
            error = "invalid_chunk_order_or_size"; return false;
        }
        try {
            for (const auto& value : entities) {
                auto entity = parseEntity(value, desired_.width, desired_.height);
                if (!desired_.entities.emplace(entity.id, std::move(entity)).second)
                    throw std::invalid_argument("duplicate_entity");
            }
            for (const auto& value : terrain) {
                const int x = value.at("x"), y = value.at("y");
                if (x < 0 || y < 0 || x >= desired_.width || y >= desired_.height)
                    throw std::invalid_argument("invalid_terrain_cell");
            }
        } catch (const std::exception& exception) {
            error = exception.what();
            active_ = false;
            return false;
        }
        desired_.terrainCount += static_cast<int>(terrain.size());
        ++received_;
        seen_.insert(operation);
        return true;
    }
    bool finish(int entities, int terrain, DesiredWorld& result, std::string& error) {
        if (!active_ || received_ != expected_ || entities != static_cast<int>(desired_.entities.size())
            || terrain != desired_.terrainCount || terrain > desired_.width * desired_.height) {
            error = "incomplete_snapshot"; return false;
        }
        result = std::move(desired_);
        active_ = false;
        return true;
    }
    void cancel() { active_ = false; desired_ = DesiredWorld{}; seen_.clear(); }
    bool active() const { return active_; }
    const std::string& session() const { return desired_.session; }
    uint64_t revision() const { return desired_.revision; }
private:
    DesiredWorld desired_;
    int expected_ = 0, received_ = 0;
    bool active_ = false;
    std::set<std::string> seen_;
};

struct ReconcilePlan {
    std::vector<std::string> keep, create, retire, changed;
};

inline ReconcilePlan planReconciliation(const DesiredWorld& previous, const DesiredWorld& next) {
    ReconcilePlan plan;
    const bool sameSession = previous.session == next.session;
    for (const auto& [id, prior] : previous.entities) {
        if (!sameSession || !next.entities.count(id)) plan.retire.push_back(id);
    }
    for (const auto& [id, desired] : next.entities) {
        const auto found = previous.entities.find(id);
        if (!sameSession || found == previous.entities.end()) plan.create.push_back(id);
        else if (found->second.raw == desired.raw) plan.keep.push_back(id);
        else plan.changed.push_back(id);
    }
    return plan;
}

} // namespace starcoaster
