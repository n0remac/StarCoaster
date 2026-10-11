#pragma once

#include <algorithm>
#include <cmath>
#include <fstream>
#include <limits>
#include <map>
#include <queue>
#include <sstream>
#include <string>
#include <utility>
#include <vector>

// Compact grid produced from actual OpenRCT2 tile elements by park_navigation.py.
// Coordinates exposed here are OpenBW pixels; the transform is in the file.
class ParkAssaultNavigation {
public:
    struct Point { int x = 0; int y = 0; };

    bool load(const std::string& path) {
        std::ifstream file(path);
        std::string magic;
        int version = 0, targetCount = 0;
        if (!(file >> magic >> version >> revision_ >> x0_ >> y0_ >> width_ >> height_ >> offsetX_ >> offsetY_ >> targetCount)
            || magic != "PARKGRID" || version != 1 || revision_ != 1
            || width_ <= 0 || height_ <= 0 || width_ > 1024 || height_ > 1024
            || targetCount < 1 || targetCount > 8) return false;
        for (int i = 0; i < targetCount; ++i) {
            std::string label, id;
            Point point;
            if (!(file >> label >> id >> point.x >> point.y) || label != "TARGET"
                || targets_.count(id)) return false;
            targets_[id] = point;
            targetOrder_.push_back(id);
        }
        raw_.resize(height_);
        for (auto& row : raw_) {
            if (!(file >> row) || static_cast<int>(row.size()) != width_) return false;
            for (char cell : row) {
                if (cell != '.' && cell != '#' && (cell < '1' || cell >= '1' + targetCount))
                    return false;
            }
        }
        rebuildClearance();
        return true;
    }

    int revision() const { return revision_; }
    Point target(const std::string& id) const { return targets_.at(id); }
    bool hasTarget(const std::string& id) const { return targets_.count(id) != 0; }

    bool applyConfirmedDemolition(const std::string& id, int revision) {
        if (revision != revision_ + 1 || !hasTarget(id) || cleared_.count(id)) return false;
        const char symbol = static_cast<char>('1' + std::distance(targetOrder_.begin(),
            std::find(targetOrder_.begin(), targetOrder_.end(), id)));
        for (auto& row : raw_) for (char& cell : row) if (cell == symbol) cell = '.';
        cleared_[id] = true;
        revision_ = revision;
        rebuildClearance();
        return true;
    }

    bool passableBW(Point point) const {
        const int x = cellX(point), y = cellY(point);
        return x >= x0_ && y >= y0_ && x < x0_ + width_ && y < y0_ + height_
            && safe_[index(x, y)] != 0;
    }
    bool directSafeBW(Point from, Point to) const {
        const int ax = cellX(from), ay = cellY(from), bx = cellX(to), by = cellY(to);
        const int steps = static_cast<int>(std::ceil(std::hypot(bx - ax, by - ay) * 2));
        for (int i = 0; i <= steps; ++i) {
            const double t = steps ? static_cast<double>(i) / steps : 0;
            const int x = static_cast<int>(std::lround(ax + (bx - ax) * t));
            const int y = static_cast<int>(std::lround(ay + (by - ay) * t));
            if (x < x0_ || y < y0_ || x >= x0_ + width_ || y >= y0_ + height_
                || !safe_[index(x, y)]) return false;
        }
        return true;
    }

    std::vector<Point> route(Point from, Point to) const {
        const int sx = cellX(from), sy = cellY(from), tx = cellX(to), ty = cellY(to);
        if (!passable(sx, sy)) return {};
        const int total = width_ * height_;
        std::vector<double> scores(total, std::numeric_limits<double>::infinity());
        std::vector<int> previous(total, -1);
        using Entry = std::pair<double, int>;
        std::priority_queue<Entry, std::vector<Entry>, std::greater<Entry>> queue;
        const int source = index(sx, sy);
        scores[source] = 0;
        queue.push({ 0, source });
        int reached = -1;
        static const int steps[8][2] = { { 1, 0 }, { -1, 0 }, { 0, 1 }, { 0, -1 },
            { 1, 1 }, { 1, -1 }, { -1, 1 }, { -1, -1 } };
        while (!queue.empty()) {
            const auto [priority, current] = queue.top();
            queue.pop();
            const int x = current % width_ + x0_, y = current / width_ + y0_;
            const double estimate = std::hypot(std::max(std::abs(x - tx) - 2, 0),
                                               std::max(std::abs(y - ty) - 2, 0));
            if (priority > scores[current] + estimate + 0.001) continue;
            if (std::abs(x - tx) <= 2 && std::abs(y - ty) <= 2 && passable(x, y)) {
                reached = current; break;
            }
            for (const auto& step : steps) {
                const int nx = x + step[0], ny = y + step[1];
                if (!passable(nx, ny)) continue;
                if (step[0] && step[1] && (!passable(x + step[0], y) || !passable(x, y + step[1]))) continue;
                const int next = index(nx, ny);
                const double score = scores[current] + std::hypot(step[0], step[1]);
                if (score + 0.0001 < scores[next]) {
                    scores[next] = score;
                    previous[next] = current;
                    const double h = std::hypot(std::max(std::abs(nx - tx) - 2, 0),
                                                std::max(std::abs(ny - ty) - 2, 0));
                    queue.push({ score + h, next });
                }
            }
        }
        if (reached < 0) return {};
        std::vector<int> path;
        for (int at = reached; at >= 0; at = previous[at]) path.push_back(at);
        std::reverse(path.begin(), path.end());
        std::vector<int> smooth{ path.front() };
        for (size_t at = 0; at + 1 < path.size();) {
            size_t farthest = at + 1;
            for (size_t candidate = path.size() - 1; candidate > at + 1; --candidate) {
                if (lineClear(path[at], path[candidate])) { farthest = candidate; break; }
            }
            smooth.push_back(path[farthest]);
            at = farthest;
        }
        std::vector<Point> result;
        for (size_t i = 0; i < smooth.size(); ++i) {
            const int a = smooth[i];
            const Point end = { (a % width_ + x0_) * 8 + 4 - offsetX_,
                                (a / width_ + y0_) * 8 + 4 - offsetY_ };
            if (!result.empty()) {
                const Point start = result.back();
                const int pieces = std::max(1, static_cast<int>(std::ceil(std::hypot(end.x - start.x,
                                                                                     end.y - start.y) / 48.0)));
                for (int part = 1; part < pieces; ++part) {
                    result.push_back({ start.x + (end.x - start.x) * part / pieces,
                                       start.y + (end.y - start.y) * part / pieces });
                }
            }
            result.push_back(end);
        }
        return result;
    }

private:
    int index(int x, int y) const { return (y - y0_) * width_ + x - x0_; }
    int cellX(Point point) const { return (point.x + offsetX_) / 8; }
    int cellY(Point point) const { return (point.y + offsetY_) / 8; }
    bool passable(int x, int y) const {
        return x >= x0_ && y >= y0_ && x < x0_ + width_ && y < y0_ + height_
            && clear_[index(x, y)] != 0;
    }
    void rebuildClearance() {
        clear_.assign(width_ * height_, 0);
        safe_.assign(width_ * height_, 0);
        for (int y = y0_; y < y0_ + height_; ++y) for (int x = x0_; x < x0_ + width_; ++x) {
            bool valid = true;
            bool safe = true;
            for (int dy = -3; dy <= 3; ++dy) for (int dx = -3; dx <= 3; ++dx) {
                if (dx * dx + dy * dy > 9) continue;
                const int nx = x + dx, ny = y + dy;
                if (nx < x0_ || ny < y0_ || nx >= x0_ + width_ || ny >= y0_ + height_
                    || raw_[ny - y0_][nx - x0_] != '.') {
                    valid = false;
                    if (dx * dx + dy * dy <= 1) safe = false;
                }
            }
            clear_[index(x, y)] = valid ? 1 : 0;
            safe_[index(x, y)] = safe ? 1 : 0;
        }
    }
    bool lineClear(int a, int b) const {
        const int ax = a % width_ + x0_, ay = a / width_ + y0_;
        const int bx = b % width_ + x0_, by = b / width_ + y0_;
        const int steps = static_cast<int>(std::ceil(std::hypot(bx - ax, by - ay) * 2));
        for (int i = 0; i <= steps; ++i) {
            const double t = steps ? static_cast<double>(i) / steps : 0;
            if (!passable(static_cast<int>(std::lround(ax + (bx - ax) * t)),
                          static_cast<int>(std::lround(ay + (by - ay) * t)))) return false;
        }
        return true;
    }

    int revision_ = 0, x0_ = 0, y0_ = 0, width_ = 0, height_ = 0;
    int offsetX_ = 0, offsetY_ = 0;
    std::vector<std::string> raw_;
    std::vector<unsigned char> clear_;
    std::vector<unsigned char> safe_;
    std::map<std::string, Point> targets_;
    std::vector<std::string> targetOrder_;
    std::map<std::string, bool> cleared_;
};
