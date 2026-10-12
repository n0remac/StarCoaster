#include "WorldState.h"

#include <cassert>
#include <iostream>

using namespace starcoaster;

static Json entity(const std::string& id, int x = 32) {
    return {{"id", id}, {"source", "openrct2"}, {"source_id", "ride:1"},
        {"kind", "ride"}, {"destructible", true},
        {"combat", {{"targetable", true}, {"health", 100}}},
        {"collision", {{"blocks", true}}},
        {"geometry", {{"rects", Json::array({{{"x", x}, {"y", 32}, {"width", 32}, {"height", 32}}})}}}};
}

int main() {
    SnapshotStager stage;
    std::string error;
    DesiredWorld first, second;
    assert(stage.begin("session", 1, 8, 8, 1, "", 0, error));
    assert(stage.chunk("op:1", 0, Json::array({entity("ride#1")}), Json::array(), error));
    assert(stage.chunk("op:1", 0, Json::array({entity("ride#1")}), Json::array(), error));
    assert(stage.finish(1, 0, first, error));
    assert(!stage.begin("session", 0, 8, 8, 1, first.session, first.revision, error));
    assert(stage.begin("session", 2, 8, 8, 1, first.session, first.revision, error));
    assert(!stage.chunk("bad", 0, Json::array({entity("ride#1", 300)}), Json::array(), error));
    assert(!stage.finish(1, 0, second, error));
    assert(stage.begin("session", 2, 8, 8, 1, first.session, first.revision, error));
    assert(stage.chunk("op:2", 0, Json::array({entity("ride#1"), entity("ride#2", 64)}), Json::array(), error));
    assert(stage.finish(2, 0, second, error));
    auto plan = planReconciliation(first, second);
    assert(plan.keep.size() == 1 && plan.keep[0] == "ride#1");
    assert(plan.create.size() == 1 && plan.create[0] == "ride#2");
    assert(plan.retire.empty());
    DesiredWorld rebuilt = second;
    rebuilt.entities.erase("ride#1");
    rebuilt.entities.emplace("ride#3", parseEntity(entity("ride#3"), 8, 8));
    plan = planReconciliation(second, rebuilt);
    assert(plan.retire.size() == 1 && plan.retire[0] == "ride#1");
    assert(plan.create.size() == 1 && plan.create[0] == "ride#3");
    std::cout << "world state tests passed\n";
}
