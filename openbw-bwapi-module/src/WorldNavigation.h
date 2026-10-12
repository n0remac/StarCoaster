#pragma once

#include "WorldState.h"

#include <algorithm>
#include <map>
#include <string>
#include <vector>

namespace starcoaster {

// Count overlapping 8-pixel collision contributions before submitting a
// complete mask to OpenBW's native VF4 walkability and region builder.
class NavigationAdapter {
public:
    void reset(int width, int height) {
        width_ = width * 4;
        height_ = height * 4;
        counts_.assign(static_cast<size_t>(width_) * height_, 0);
        terrain_.assign(counts_.size(), 0);
        obstacles_.clear();
        native_ = false;
    }
    void replace(const DesiredWorld& world) {
        reset(world.width, world.height);
        for (int y = 0; y < world.height; ++y)
            for (int x = 0; x < world.width; ++x)
                if (world.unwalkableTerrain.size() == static_cast<size_t>(world.width * world.height)
                    && world.unwalkableTerrain[static_cast<size_t>(y) * world.width + x])
                    for (int sy = 0; sy < 4; ++sy)
                        for (int sx = 0; sx < 4; ++sx)
                            terrain_[(y * 4 + sy) * width_ + x * 4 + sx] = 1;
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
                if (counts_[row * width_ + column] > 0 || terrain_[row * width_ + column]) return true;
        return false;
    }
    size_t objects() const { return obstacles_.size(); }
    const std::map<std::string, std::vector<Rect>>& obstacles() const { return obstacles_; }
    std::vector<uint8_t> mask() const {
        std::vector<uint8_t> result(counts_.size());
        for (size_t i = 0; i < result.size(); ++i)
            result[i] = counts_[i] > 0 || terrain_[i];
        return result;
    }
    void markNative(bool applied) { native_ = applied; }
    const char* capability() const { return native_ ? "native" : "metadata_only"; }
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
    std::vector<uint8_t> terrain_;
    std::map<std::string, std::vector<Rect>> obstacles_;
    bool native_ = false;
};

} // namespace starcoaster
