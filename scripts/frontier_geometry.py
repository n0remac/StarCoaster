"""Validate the exported Frontier park edges and connected visitor routes."""

from collections import Counter


def wall_edge(element):
    x, y, direction = element["x"], element["y"], element["direction"]
    if direction == 0:
        return tuple(sorted(((x, y), (x, y + 1))))
    if direction == 1:
        return tuple(sorted(((x, y + 1), (x + 1, y + 1))))
    if direction == 2:
        return tuple(sorted(((x + 1, y), (x + 1, y + 1))))
    if direction == 3:
        return tuple(sorted(((x, y), (x + 1, y))))
    raise ValueError(f"invalid wall direction {direction}")


def validate(export, fixture):
    if fixture.get("layout_version") != 2:
        raise ValueError("playable park layout is stale; regenerate it")
    elements = export["elements"]
    walls = [item for item in elements if item["type"] == "wall"]
    paths = {(item["x"], item["y"]) for item in elements if item["type"] == "footpath"}
    edges = [wall_edge(item) for item in walls]
    if len(edges) != len(set(edges)):
        raise ValueError("overlapping wall edges")
    degree = Counter(vertex for edge in edges for vertex in edge)
    if any(degree[a] == degree[b] == 1 for a, b in edges):
        raise ValueError("floating wall segment")
    for corner in ((12, 12), (54, 12), (12, 54), (54, 54), (35, 16), (47, 16)):
        if degree[corner] != 2:
            raise ValueError(f"disconnected wall corner {corner}: degree={degree[corner]}")
    gate = tuple(sorted(((28, 35), (28, 36))))
    if gate not in edges or degree[(28, 35)] < 2 or degree[(28, 36)] < 2:
        raise ValueError("destructible defense gate is disconnected")
    if not paths:
        raise ValueError("park has no paths")
    visited = {next(iter(paths))}
    todo = list(visited)
    while todo:
        x, y = todo.pop()
        for point in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if point in paths and point not in visited:
                visited.add(point)
                todo.append(point)
    if visited != paths:
        raise ValueError(f"disconnected paths: {len(paths) - len(visited)} tiles")
    tracks = {(item["x"], item["y"]) for item in elements if item["type"] == "track"}
    if tracks & paths:
        raise ValueError(f"paths overlap ride track: {tracks & paths}")
    for x, y in ((15, 30), (16, 30), (17, 30), (15, 31), (16, 31), (17, 31)):
        if (x, y) in tracks:
            raise ValueError("Marine spawn overlaps ride track")
    return {"wall_segments": len(edges), "wall_vertices": len(degree),
            "path_tiles": len(paths), "ride_tiles": len(tracks),
            "defense_gate": [28, 35]}
