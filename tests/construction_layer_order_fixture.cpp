#include <cassert>
#include <vector>

#include "BridgeConstructionLayers.h"

struct Node
{
    int id;
    int layer; // 0 ordinary, 1 SCV, 2 unfinished, 3 completed
    int site;
    Node* NextQuadrantEntry = nullptr;
};

static void check(std::vector<Node> nodes, const std::vector<int>& expected)
{
    for (std::size_t i = 1; i < nodes.size(); ++i)
        nodes[i - 1].NextQuadrantEntry = &nodes[i];
    Node* head = nodes.data();
    BridgeOrderConstructionLayers(head,
        [](const Node* node) { return node->layer == 1; },
        [](const Node* node) { return node->layer == 2; },
        [](const Node* node) { return node->layer == 3; },
        [](const Node* scv, const Node* building) { return scv->site == building->site; });
    std::vector<int> actual;
    for (auto* node = head; node; node = node->NextQuadrantEntry)
    {
        assert(actual.size() < nodes.size()); // No accidental paint-list cycle.
        actual.push_back(node->id);
    }
    assert(actual == expected);
}

int main()
{
    // A plate currently sorted in front of the worker must move behind it.
    check({ { 1, 1, 7 }, { 2, 2, 7 }, { 3, 0, 0 } }, { 2, 1, 3 });
    // Completed scenery must draw after the worker, even if initially behind.
    check({ { 1, 3, 7 }, { 2, 1, 7 }, { 3, 0, 0 } }, { 2, 1, 3 });
    // Both constraints hold at once, preserving tile and unrelated draw order.
    check({ { 1, 3, 7 }, { 2, 3, 7 }, { 3, 0, 0 }, { 4, 1, 7 },
            { 5, 0, 0 }, { 6, 2, 7 }, { 7, 2, 7 }, { 8, 0, 0 } },
          { 3, 6, 7, 4, 1, 2, 5, 8 });
    // A nearby building on another site is untouched.
    check({ { 1, 3, 8 }, { 2, 1, 7 }, { 3, 2, 8 } }, { 1, 2, 3 });
}
