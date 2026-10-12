#include "WorldAssaultController.h"

#include <cassert>

int main() {
    WorldAssaultController controller;
    assert(!controller.active(100)); // Generic world sessions have no assault policy.
    assert(!controller.start(100, 0));
    controller.configure("openrct2:ride:0#1");
    assert(!controller.active(100));
    assert(controller.start(100, 144));
    assert(!controller.active(243));
    assert(controller.active(244));
    controller.configure(""); // A new generic session retires the old encounter.
    assert(!controller.active(1000));
}
