#pragma once

#include "WorldState.h"

#include <algorithm>
#include <map>
#include <string>
#include <vector>

namespace starcoaster {

// Geometry registry for the future native engine hook. Counting overlapping
// contributions ensures removing one object cannot clear another footprint.
// The current OpenBW pathfinder does not consume this registry.
class NavigationAdapter {
public:
    void replace(const DesiredWorld& world) {
        width_ = world.width * 4;
        height_ = world.height * 4;
        counts_.assign(width_ * height_, 0);
        obstacles_.clear();
        for (const auto& [id, entity] : world.entities)
            if (entity.blocks && !entity.rectangles.empty()) upsert(id, entity.rectangles);
    }
    bool upsert(const std::string& id, const std::vector<Rect>& rectangles) {
        if (id.empty() || width_ < 1 || height_ < 1) return false;
        for (const auto& rectangle : rectangles) {
            if (rectangle.x < 0 || rectangle.y < 0 || rectangle.width < 1 || rectangle.height < 1
                || rectangle.x + rectangle.width > width_ * 8
                || rectangle.y + rectangle.height > height_ * 8) return false;
        }
        remove(id);
        obstacles_[id] = rectangles;
        for (const auto& rectangle : rectangles) contribute(rectangle, 1);
        return true;
    }
    bool remove(const std::string& id) {
        const auto found = obstacles_.find(id);
        if (found == obstacles_.end()) return false;
        for (const auto& rectangle : found->second) contribute(rectangle, -1);
        obstacles_.erase(found);
        return true;
    }
    bool blocked(int x, int y, int clearance = 0) const {
        if (x < clearance || y < clearance || x + clearance >= width_ * 8
            || y + clearance >= height_ * 8) return true;
        const int fromX = std::max(0, (x - clearance) / 8);
        const int toX = std::min(width_ - 1, (x + clearance) / 8);
        const int fromY = std::max(0, (y - clearance) / 8);
        const int toY = std::min(height_ - 1, (y + clearance) / 8);
        for (int row = fromY; row <= toY; ++row)
            for (int column = fromX; column <= toX; ++column)
                if (counts_[row * width_ + column] > 0) return true;
        return false;
    }
    size_t objects() const { return obstacles_.size(); }
    const std::map<std::string, std::vector<Rect>>& obstacles() const { return obstacles_; }
    const char* capability() const { return "metadata_only"; }
private:
    void contribute(const Rect& rectangle, int amount) {
        const int fromX = rectangle.x / 8;
        const int fromY = rectangle.y / 8;
        const int toX = (rectangle.x + rectangle.width - 1) / 8;
        const int toY = (rectangle.y + rectangle.height - 1) / 8;
        for (int y = fromY; y <= toY; ++y)
            for (int x = fromX; x <= toX; ++x)
                counts_[y * width_ + x] += amount;
    }
    int width_ = 0, height_ = 0;
    std::vector<int> counts_;
    std::map<std::string, std::vector<Rect>> obstacles_;
};

} // namespace starcoaster
