#pragma once

#include "WorldState.h"

#include <algorithm>
#include <cstdint>
#include <map>
#include <string>
#include <vector>

namespace starcoaster {

// The bridge sends the same packed 8-pixel mask to both simulation players.
// Hex chunks bound each protocol line; no million-element JSON array is sent.
class NavigationMaskReceiver {
public:
    bool begin(int width, int height, int chunks, const std::string& hash) {
        reset();
        if (width < 1 || height < 1 || width > 256 || height > 256 || chunks < 1 || chunks > 256
            || hash.size() != 16 || hash.find_first_not_of("0123456789abcdef") != std::string::npos)
            return false;
        width_ = width; height_ = height; chunks_ = chunks; hash_ = hash;
        return true;
    }
    bool chunk(int index, const std::string& hex) {
        if (!width_ || index != received_ || hex.empty() || hex.size() > 12000 || hex.size() % 2)
            return false;
        if (packed_.size() + hex.size() / 2 > static_cast<size_t>((width_ * height_ * 16 + 7) / 8))
            return false;
        for (size_t i = 0; i < hex.size(); i += 2) {
            const int high = digit(hex[i]), low = digit(hex[i + 1]);
            if (high < 0 || low < 0) return false;
            packed_.push_back(static_cast<uint8_t>((high << 4) | low));
        }
        ++received_;
        return true;
    }
    bool finish(std::vector<uint8_t>& blocked) {
        if (!width_ || received_ != chunks_ ||
            packed_.size() != static_cast<size_t>((width_ * height_ * 16 + 7) / 8) ||
            hashOf(packed_) != hash_) return false;
        const size_t count = static_cast<size_t>(width_) * height_ * 16;
        blocked.resize(count);
        for (size_t i = 0; i < count; ++i)
            blocked[i] = (packed_[i / 8] >> (i % 8)) & 1;
        reset();
        return true;
    }
    void reset() { width_ = height_ = chunks_ = received_ = 0; hash_.clear(); packed_.clear(); }
    static std::string hashOf(const std::vector<uint8_t>& data) {
        uint64_t hash = 14695981039346656037ULL;
        for (auto byte : data) { hash ^= byte; hash *= 1099511628211ULL; }
        const char digits[] = "0123456789abcdef";
        std::string result(16, '0');
        for (int i = 15; i >= 0; --i) { result[i] = digits[hash & 15]; hash >>= 4; }
        return result;
    }
private:
    static int digit(char value) {
        if (value >= '0' && value <= '9') return value - '0';
        if (value >= 'a' && value <= 'f') return value - 'a' + 10;
        return -1;
    }
    int width_ = 0, height_ = 0, chunks_ = 0, received_ = 0;
    std::string hash_;
    std::vector<uint8_t> packed_;
};

// Count overlapping 8-pixel collision contributions before submitting a
// complete mask to OpenBW's native VF4 walkability and region builder.
class NavigationAdapter {
public:
    void reset(int width, int height) {
        width_ = width * 4;
        height_ = height * 4;
        counts_.assign(static_cast<size_t>(width_) * height_, 0);
        terrain_.assign(counts_.size(), 0);
        maskOverride_.clear();
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
                if (!maskOverride_.empty() ? maskOverride_[row * width_ + column]
                    : (counts_[row * width_ + column] > 0 || terrain_[row * width_ + column])) return true;
        return false;
    }
    size_t objects() const { return obstacles_.size(); }
    const std::map<std::string, std::vector<Rect>>& obstacles() const { return obstacles_; }
    std::vector<uint8_t> mask() const {
        if (!maskOverride_.empty()) return maskOverride_;
        std::vector<uint8_t> result(counts_.size());
        for (size_t i = 0; i < result.size(); ++i)
            result[i] = counts_[i] > 0 || terrain_[i];
        return result;
    }
    void markNative(bool applied) { native_ = applied; }
    bool installMask(const std::vector<uint8_t>& mask) {
        if (mask.size() != counts_.size()) return false;
        maskOverride_ = mask;
        return true;
    }
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
    std::vector<uint8_t> maskOverride_;
    std::map<std::string, std::vector<Rect>> obstacles_;
    bool native_ = false;
};

} // namespace starcoaster
