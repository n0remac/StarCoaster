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
    if fixture.get("layout_version") != 3:
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
    bounds = export["bounds"]
    heights = export["elevation_rows"]
    slopes = export["slope_rows"]
    water = export["water_rows"]
    if (len(heights), len(slopes), len(water)) != (48, 48, 48) or any(
        len(row) != 48 for grid in (heights, slopes, water) for row in grid
    ):
        raise ValueError("incomplete 64x64 park terrain export")

    def surface(x, y):
        row, col = y - bounds["min_y"], x - bounds["min_x"]
        return heights[row][col], slopes[row][col], water[row][col]

    raised = {(x, y) for y in range(8, 56) for x in range(8, 56)
              if surface(x, y)[0] == 128}
    if raised != {(x, y) for y in range(30, 35) for x in range(14, 25)}:
        raise ValueError("Marine defensive ridge is absent or misplaced")
    ramps = {(x, y): surface(x, y)[1] for y in range(8, 56) for x in range(8, 56)
             if surface(x, y)[1]}
    expected_ramps = ({(x, 29): 6 for x in range(14, 19)} |
                      {(x, 35): 9 for x in range(14, 19)} |
                      {(25, y): 3 for y in range(30, 35)})
    if ramps != expected_ramps or any(surface(x, y)[2] for y in range(8, 56) for x in range(8, 56)):
        raise ValueError("ridge slopes or water differ from the playable layout")
    for x, y in ((15, 30), (16, 30), (17, 30), (15, 31), (16, 31), (17, 31)):
        if (x, y) not in raised:
            raise ValueError("Marine spawn is not on the ridge")

    directions = {6: 3, 9: 1, 3: 2}
    for item in elements:
        x, y = item["x"], item["y"]
        base, slope, _ = surface(x, y)
        if item["type"] == "footpath":
            if item["z"] != base or item.get("slope_direction") != directions.get(slope):
                raise ValueError(f"footpath does not follow terrain at {x},{y}")
        elif (x, y) in raised and item["type"] in {"small_scenery", "large_scenery", "wall"}:
            if item["z"] != base:
                raise ValueError(f"construction elevation does not match ridge at {x},{y}")

    # Native corner heights determine connection. The direct western edge is
    # a cliff, while the eastern side slope must join low and raised ground.
    def corners(x, y):
        base, slope, _ = surface(x, y)
        return tuple(base + (16 if slope & bit else 0) for bit in (1, 8, 4, 2))

    def connected(x, y, nx, ny):
        a, b = corners(x, y), corners(nx, ny)
        if nx == x + 1:
            return a[1] == b[0] and a[2] == b[3]
        if nx == x - 1:
            return b[1] == a[0] and b[2] == a[3]
        if ny == y + 1:
            return a[2] == b[1] and a[3] == b[0]
        return b[2] == a[1] and b[3] == a[0]

    if connected(13, 32, 14, 32) or not connected(26, 32, 25, 32) or not connected(25, 32, 24, 32):
        raise ValueError("cliff or eastern slope has invalid edge geometry")
    reached = {(26, 32)}
    todo = [(26, 32)]
    while todo:
        x, y = todo.pop()
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if 8 <= nx <= 55 and 8 <= ny <= 55 and (nx, ny) not in reached and connected(x, y, nx, ny):
                reached.add((nx, ny))
                todo.append((nx, ny))
    if (20, 32) not in reached or (15, 31) not in reached:
        raise ValueError("defensive ridge cannot be reached through a slope")
    return {"wall_segments": len(edges), "wall_vertices": len(degree),
            "path_tiles": len(paths), "ride_tiles": len(tracks),
            "defense_gate": [28, 35], "raised_tiles": len(raised),
            "slope_tiles": len(ramps)}
