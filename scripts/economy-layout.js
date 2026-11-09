/* Deterministic, bounded ordinary-park economy site search. OpenRCT2 supplies
 * the source geometry; OpenBW remains the authority for native gameplay. */
(function (root) {
    'use strict';
    const POLICY_VERSION = 2;
    const SPAN_X = 22, SPAN_Y = 9, MAX_ROUTE_CHECKS = 4096;
    const TEMPLATE = [
        { id: 'base', type: 'terran_command_center', x: 0, y: 0, w: 4, h: 3 },
        { id: 'worker-a', type: 'terran_scv', x: 5, y: 1, w: 1, h: 1 },
        { id: 'worker-b', type: 'terran_scv', x: 6, y: 1, w: 1, h: 1 },
        { id: 'worker-c', type: 'terran_scv', x: 5, y: 2, w: 1, h: 1 },
        { id: 'worker-d', type: 'terran_scv', x: 6, y: 2, w: 1, h: 1 },
        { id: 'mineral-a', type: 'mineral_field', x: 8, y: 0, w: 2, h: 1, amount: 1500 },
        { id: 'mineral-b', type: 'mineral_field', x: 11, y: 0, w: 2, h: 1, amount: 1500 },
        { id: 'mineral-c', type: 'mineral_field', x: 14, y: 0, w: 2, h: 1, amount: 1500 },
        { id: 'mineral-d', type: 'mineral_field', x: 8, y: 4, w: 2, h: 1, amount: 1500 },
        { id: 'mineral-e', type: 'mineral_field', x: 11, y: 4, w: 2, h: 1, amount: 1500 },
        { id: 'mineral-f', type: 'mineral_field', x: 14, y: 4, w: 2, h: 1, amount: 1500 },
        { id: 'geyser', type: 'vespene_geyser', x: 18, y: 1, w: 4, h: 2, amount: 5000 },
        { id: 'depot-space', x: 0, y: 5, w: 3, h: 2 },
        { id: 'barracks-space', x: 4, y: 6, w: 4, h: 3 },
    ];
    const DIRECTIONS = [[1, 0], [-1, 0], [0, 1], [0, -1]];

    function hashSeed(seed) {
        let hash = 2166136261;
        for (const character of String(seed)) {
            hash ^= character.charCodeAt(0);
            hash = Math.imul(hash, 16777619);
        }
        return hash >>> 0;
    }

    function scan(map) {
        const width = map.size.x, height = map.size.y, cells = new Array(width * height);
        for (let y = 0; y < height; y++) for (let x = 0; x < width; x++) {
            const tile = map.getTile(x, y);
            let surface = null, occupied = false, walkBlocked = false;
            if (tile) for (let index = 0; index < tile.numElements; index++) {
                const element = tile.getElement(index);
                if (element.type === 'surface') surface = element;
                else {
                    occupied = true;
                    if (element.type !== 'footpath') walkBlocked = true;
                }
            }
            const owned = !!(surface && (surface.ownership & 2));
            const dry = !!(surface && !surface.waterHeight);
            const flat = !!(surface && !surface.slope);
            cells[y * width + x] = { build: owned && dry && flat && !occupied,
                walk: owned && dry && flat && !walkBlocked,
                z: surface ? surface.baseHeight : -1 };
        }
        return cells;
    }

    function transformed(originX, originY, flipX, flipY) {
        return TEMPLATE.map(entry => ({ ...entry,
            x: originX + (flipX ? SPAN_X - entry.x - entry.w : entry.x),
            y: originY + (flipY ? SPAN_Y - entry.y - entry.h : entry.y) }));
    }

    function clearFootprints(entries, cells, width) {
        let siteHeight = null;
        for (const entry of entries) {
            for (let y = entry.y; y < entry.y + entry.h; y++)
                for (let x = entry.x; x < entry.x + entry.w; x++) {
                    const cell = cells[y * width + x];
                    if (!cell.build || (siteHeight !== null && cell.z !== siteHeight)) return false;
                    siteHeight = cell.z;
                }
        }
        return true;
    }

    function reachable(entries, cells, width, height) {
        const lowX = Math.max(0, Math.min(...entries.map(entry => entry.x)) - 2);
        const lowY = Math.max(0, Math.min(...entries.map(entry => entry.y)) - 2);
        const highX = Math.min(width, Math.max(...entries.map(entry => entry.x + entry.w)) + 2);
        const highY = Math.min(height, Math.max(...entries.map(entry => entry.y + entry.h)) + 2);
        const occupied = new Set();
        for (const entry of entries) if (entry.type !== 'terran_scv' && entry.type) {
            for (let y = entry.y; y < entry.y + entry.h; y++)
                for (let x = entry.x; x < entry.x + entry.w; x++) occupied.add(y * width + x);
        }
        const walk = (x, y) => x >= lowX && y >= lowY && x < highX && y < highY
            && cells[y * width + x].walk && !occupied.has(y * width + x);
        const workers = entries.filter(entry => entry.type === 'terran_scv');
        const targets = entries.filter(entry => entry.type && entry.type !== 'terran_scv');
        function access(entry, visited) {
            for (let y = entry.y; y < entry.y + entry.h; y++)
                for (let x = entry.x; x < entry.x + entry.w; x++)
                    for (const [dx, dy] of DIRECTIONS) {
                        const nx = x + dx, ny = y + dy;
                        if (walk(nx, ny) && visited.has(ny * width + nx)) return true;
                    }
            return false;
        }
        for (const worker of workers) {
            if (!walk(worker.x, worker.y)) return false;
            const start = worker.y * width + worker.x, visited = new Set([start]);
            const queue = [start];
            for (let cursor = 0; cursor < queue.length; cursor++) {
                const index = queue[cursor], x = index % width, y = Math.floor(index / width);
                for (const [dx, dy] of DIRECTIONS) {
                    const nx = x + dx, ny = y + dy, next = ny * width + nx;
                    if (walk(nx, ny) && !visited.has(next)
                        && cells[next].z === cells[index].z) {
                        visited.add(next); queue.push(next);
                    }
                }
            }
            if (!targets.every(target => access(target, visited))) return false;
        }
        return true;
    }

    function candidateOrder(a, b) {
        return a.score - b.score || a.tie - b.tie || a.y - b.y || a.x - b.x
            || a.variant - b.variant;
    }

    // Reserve a whole colony yard, including larva emergence and assembly.
    // The native participants make the final path/placement decision at boot.
    function findEnemyBase(cells, width, height, seedHash, economyEntries, defenseSites) {
        const occupied = new Set(), walkOccupied = new Set();
        for (const entry of [...economyEntries, ...defenseSites]) {
            for (let y = entry.y - 2; y < entry.y + entry.h + 2; y++)
                for (let x = entry.x - 2; x < entry.x + entry.w + 2; x++)
                    occupied.add(y * width + x);
            if (entry.type !== 'terran_scv')
                for (let y = entry.y; y < entry.y + entry.h; y++)
                    for (let x = entry.x; x < entry.x + entry.w; x++)
                        walkOccupied.add(y * width + x);
        }
        const workers = economyEntries.filter(e => e.type === 'terran_scv');
        const connected = new Set(), queue = [];
        for (const worker of workers) {
            const index = worker.y * width + worker.x;
            if (!connected.has(index)) { connected.add(index); queue.push(index); }
        }
        for (let head = 0; head < queue.length; head++) {
            const current = queue[head], x = current % width, y = Math.floor(current / width);
            for (const [dx, dy] of DIRECTIONS) {
                const nx = x + dx, ny = y + dy, next = ny * width + nx;
                if (nx < 8 || ny < 8 || nx >= width - 8 || ny >= height - 8 ||
                    connected.has(next) || walkOccupied.has(next) || !cells[next].walk ||
                    cells[next].z !== cells[current].z) continue;
                connected.add(next); queue.push(next);
            }
        }
        const terranApproaches = [...connected].filter(index => !occupied.has(index))
            .map(index => ({ x: index % width, y: Math.floor(index / width),
                score: Math.min(...workers.map(worker =>
                    (worker.x - index % width) ** 2 + (worker.y - Math.floor(index / width)) ** 2)) }))
            .sort((a, b) => a.score - b.score || a.y - b.y || a.x - b.x);
        if (!terranApproaches.length) return { policy_version: 2, state: 'blocked',
            reason: 'no_valid_perimeter_site', candidates_checked: 0, structures: [] };
        const terranApproach = terranApproaches[0];
        const candidates = [];
        for (let y = 8; y + 9 <= height - 8; y++)
            for (let x = 8; x + 9 <= width - 8; x++) {
                if (Math.min(x - 8, y - 8, width - 8 - (x + 9), height - 8 - (y + 9)) > 4)
                    continue;
                let valid = true, z = null;
                for (let cy = y; cy < y + 9 && valid; cy++)
                    for (let cx = x; cx < x + 9; cx++) {
                        const index = cy * width + cx, cell = cells[index];
                        if (!cell.build || occupied.has(index) || (z !== null && cell.z !== z)) {
                            valid = false; break;
                        }
                        z = cell.z;
                    }
                if (!valid) continue;
                // The assembly yard and the Terran approach share a confirmed
                // source-height walk component. Native path checks follow boot.
                const approach = (y + 5) * width + x + 4;
                if (!connected.has(approach)) continue;
                const score = (Math.imul(x + 1, 73856093) ^ Math.imul(y + 1, 19349663)
                    ^ seedHash) >>> 0;
                candidates.push({ x, y, score });
            }
        candidates.sort((a, b) => a.score - b.score || a.y - b.y || a.x - b.x);
        if (!candidates.length) return { policy_version: 2, state: 'blocked',
            reason: 'no_valid_perimeter_site', candidates_checked: 0, structures: [] };
        const { x, y } = candidates[0];
        return { policy_version: 2, state: 'ready', seed: String(seedHash),
            candidates_checked: candidates.length,
            structures: [
                { id: 'enemy-hatchery', type: 'zerg_hatchery', tile: [x + 1, y + 1] },
                // Keep the Pool within Hatchery creep while leaving painted
                // silhouettes clear in all four OpenRCT2 rotations.
                { id: 'enemy-spawning-pool', type: 'zerg_spawning_pool', tile: [x + 1, y + 7] },
            ], supply_tile: [x + 8, y + 4], assembly_tile: [x + 4, y + 5],
            approach_tile: [x + 4, y + 8],
            terran_approach_tile: [terranApproach.x, terranApproach.y] };
    }

    // Keep only the best bounded set while scanning a 256x256 park. The root
    // is the worst candidate; replacing it preserves the same center-first
    // order as a full sort without retaining hundreds of thousands of layouts.
    function retainCandidate(heap, candidate) {
        if (heap.length < MAX_ROUTE_CHECKS) {
            let index = heap.length;
            heap.push(candidate);
            while (index > 0) {
                const parent = Math.floor((index - 1) / 2);
                if (candidateOrder(heap[parent], candidate) >= 0) break;
                heap[index] = heap[parent]; index = parent;
            }
            heap[index] = candidate;
        } else if (candidateOrder(candidate, heap[0]) < 0) {
            let index = 0;
            while (index * 2 + 1 < heap.length) {
                let child = index * 2 + 1;
                if (child + 1 < heap.length && candidateOrder(heap[child + 1], heap[child]) > 0)
                    child++;
                if (candidateOrder(candidate, heap[child]) >= 0) break;
                heap[index] = heap[child]; index = child;
            }
            heap[index] = candidate;
        }
    }

    function findEconomyLayout(map, seed) {
        const width = map.size.x, height = map.size.y;
        if (!Number.isInteger(width) || !Number.isInteger(height) || width > 256 || height > 256
            || width < 16 || height < 16) throw new Error('invalid_economy_map_size');
        const cells = scan(map), seedHash = hashSeed(seed), candidates = [];
        let checked = 0, footprintCandidates = 0;
        for (let y = 8; y + SPAN_Y <= height - 8; y++)
            for (let x = 8; x + SPAN_X <= width - 8; x++)
                // The authored E0/E2 native delivery route keeps minerals to
                // the Command Center's right. A mirrored ordinary-park site
                // mined once but left the SCV carrying at the deposit, so do
                // not publish that orientation as a playable economy.
                for (const variant of [0, 2]) {
                    checked++;
                    const entries = transformed(x, y, !!(variant & 1), !!(variant & 2));
                    if (!clearFootprints(entries, cells, width)) continue;
                    footprintCandidates++;
                    const base = entries[0], centerX = base.x * 2 + base.w - width,
                        centerY = base.y * 2 + base.h - height;
                    const tie = Math.imul(x + 1, 73856093) ^ Math.imul(y + 1, 19349663)
                        ^ Math.imul(variant + 1, 83492791) ^ seedHash;
                    retainCandidate(candidates, { entries, score: centerX * centerX + centerY * centerY,
                        tie: tie >>> 0, x, y, variant });
                }
        candidates.sort(candidateOrder);
        let routeChecks = 0;
        for (const candidate of candidates) {
            if (routeChecks >= MAX_ROUTE_CHECKS) break;
            routeChecks++;
            if (!reachable(candidate.entries, cells, width, height)) continue;
            const enemyBase = findEnemyBase(cells, width, height, seedHash,
                candidate.entries.filter(entry => entry.type), candidate.entries.filter(entry => !entry.type));
            return { policy_version: POLICY_VERSION, state: 'ready', seed: String(seed),
                candidates_checked: checked, candidates_retained: candidates.length,
                route_checks: routeChecks,
                enemy_base: enemyBase,
                starting_entities: candidate.entries.filter(entry => entry.type).map(entry => ({
                    id: entry.id, type: entry.type, tile: [entry.x, entry.y],
                    ...(entry.amount ? { amount: entry.amount } : {}) })),
                defense_sites: candidate.entries.filter(entry => !entry.type).map(entry => ({
                    id: entry.id, tile: [entry.x, entry.y], size: [entry.w, entry.h] })) };
        }
        return { policy_version: POLICY_VERSION, state: 'blocked', seed: String(seed),
            reason: footprintCandidates > MAX_ROUTE_CHECKS
                ? 'economy_search_limit' : 'no_native_valid_economy_site',
            candidates_checked: checked, candidates_retained: candidates.length,
            route_checks: routeChecks, starting_entities: [], defense_sites: [],
            enemy_base: { policy_version: 2, state: 'blocked',
                reason: 'terran_economy_blocked', structures: [] } };
    }

    root.starcoasterFindEconomyLayout = findEconomyLayout;
    if (typeof module !== 'undefined') module.exports = { findEconomyLayout, POLICY_VERSION };
})(typeof globalThis !== 'undefined' ? globalThis : this);
