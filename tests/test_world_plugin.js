const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const tiles = new Map();
function at(x, y) { const key = `${x},${y}`; if (!tiles.has(key)) tiles.set(key, [{ type: 'surface', baseHeight: 14, waterHeight: 0, surfaceObject: 1 }]); return tiles.get(key); }
at(0, 0)[0].slope = 3;
at(0, 0)[0].baseZ = 112;
at(1, 0)[0].waterHeight = 128;
let ride = { id: 17, name: 'Café 🎢 Carousel', type: 33, classification: 'ride',
    object: { identifier: 'rct2.ride.mgr1' }, status: 'closed', isEmpty: true };
let rejectNextRideDemolition = false;
at(1, 1).push({ type: 'track', ride: 17, baseHeight: 14, baseZ: 112,
    clearanceZ: 160, occupiedQuadrants: 15, trackType: 0, sequence: 0, direction: 0 });
at(1, 2).push({ type: 'track', ride: 17, baseHeight: 14, baseZ: 112,
    clearanceZ: 160, occupiedQuadrants: 15, trackType: 0, sequence: 0, direction: 0 });
at(4, 1).push({ type: 'small_scenery', object: 2, baseHeight: 14, quadrant: 0, direction: 0 });
at(6, 4).push({ type: 'small_scenery', object: 5, baseHeight: 20,
    baseZ: 160, clearanceZ: 184, occupiedQuadrants: 15, quadrant: 0, direction: 0 });
at(5, 1).push({ type: 'wall', object: 3, baseHeight: 14, direction: 1 });
at(5, 2)[0].slope = 12;
at(5, 2).push({ type: 'footpath', object: 4, surfaceObject: 4,
    baseHeight: 14, baseZ: 112, slopeDirection: 0 });
at(2, 3).push({ type: 'large_scenery', object: 1, sequence: 0, baseHeight: 14, direction: 0 });
at(3, 3).push({ type: 'large_scenery', object: 1, sequence: 1, baseHeight: 14, direction: 0 });
at(7, 7).push({ type: 'wall', object: 3, baseHeight: 14, direction: 0, isGhost: true });
at(6, 6).push({ type: 'footpath', object: 4, surfaceObject: 4,
    baseHeight: 14, baseZ: 112, clearanceZ: 144, occupiedQuadrants: 15 });
at(6, 6).push({ type: 'footpath', object: 4, surfaceObject: 4,
    baseHeight: 18, baseZ: 144, clearanceZ: 176, occupiedQuadrants: 15 });
const sent = [], actions = [], applied = [], logs = [], registered = new Map(), responses = [], subscriptions = new Map();
const shortcuts = new Map();
let selectionTool;
let squadWidgets;
let socket;
const sandbox = {
    map: { size: { x: 8, y: 8 }, get rides() { return ride ? [ride] : []; },
        getRide(id) { return ride && id === ride.id ? ride : null; },
        getTile(x, y) { const elements = at(x, y); return { numElements: elements.length,
            getElement(index) { return elements[index]; } }; } },
    objectManager: { getAllObjects(kind) {
        if (kind === 'large_scenery') return [{ index: 1, identifier: 'rct2.scenery_large.test',
            tiles: [{ offset: { x: 0, y: 0, z: 0 } }, { offset: { x: 32, y: 0, z: 0 } }] }];
        if (kind === 'small_scenery') return [
            { index: 2, identifier: 'rct2.scenery_small.tree' },
            { index: 5, identifier: 'rct2.scenery_small.no_supports', flags: 1 << 20 }];
        if (kind === 'wall') return [{ index: 3, identifier: 'rct2.scenery_wall.wall' }];
        return [];
    } },
    network: { mode: 'server', currentPlayer: { id: 1 }, players: [{ id: 1 }], createSocket() {
        socket = { handlers: {}, on(kind, callback) { this.handlers[kind] = callback; },
            connect(_port, _host, callback) { callback(); }, destroy() {},
            write(line) { const m = JSON.parse(line); sent.push(m);
                responses.push(JSON.stringify({ v: 1, kind: 'world.ack', session: m.session,
                    payload: { op_id: m.op_id, accepted: true } }) + '\n');
            } }; return socket;
    } },
    rtsBridge: { version: 4, assetVersion: 3, invalidateAnimation() {}, applySnapshot(snapshot) { applied.push(snapshot); },
        hitTest(x, y) { return x === 32 && y === 32 ? 'openbw:3001' : null; } },
    ui: { tileSelection: { tiles: [] }, openWindow(desc) { squadWidgets = desc.widgets;
            return { findWidget() { return { text: '' }; } }; },
        registerShortcut(shortcut) { shortcuts.set(shortcut.id, shortcut); },
        activateTool(tool) { selectionTool = tool; }, showError() {} },
    context: { registerAction(name, query, execute) { registered.set(name, { query, execute }); },
        subscribe(name, callback) { const previous = subscriptions.get(name);
            subscriptions.set(name, previous ? function (event) { previous(event); callback(event); } : callback);
        }, executeAction(name, args, callback) { actions.push({ name, args });
            if (name === 'ridedemolish') {
                if (rejectNextRideDemolition) {
                    rejectNextRideDemolition = false;
                    callback({ error: 1, errorMessage: 'native rejection' });
                    return;
                }
                assert.equal(args.ride, 17); ride = null;
                for (const elements of tiles.values()) for (let i = elements.length - 1; i >= 0; i--)
                    if (elements[i].type === 'track') elements.splice(i, 1);
                callback({}); return;
            }
            if (name === 'wallremove') {
                const elements = at(5, 1);
                for (let i = elements.length - 1; i >= 0; i--)
                    if (elements[i].type === 'wall') elements.splice(i, 1);
                callback({}); return;
            }
            const action = registered.get(name); assert.ok(action, name);
            const result = action.query({ player: 1, args }); if (!result.error) action.execute({ player: 1, args });
            callback(result);
        } },
    console: { log(line) { logs.push(line); } }, registerPlugin(plugin) { plugin.main(); },
};
vm.runInNewContext(fs.readFileSync('openrct2-plugin/rts-bridge.js', 'utf8'), sandbox);
function drain() { while (responses.length) socket.handlers.data(responses.shift()); }
drain();
const begin = sent.find(m => m.kind === 'world.snapshot.begin');
assert.ok(begin, 'discovery begins without a scenario configuration');
const all = sent.filter(m => m.kind === 'world.snapshot.chunk').flatMap(m => m.payload.entities || []);
assert.equal(all.find(e => e.kind === 'ride').name, 'Café 🎢 Carousel', 'ride name is exported for authored objectives');
const geometryMetric = logs.find(line => line.startsWith('WORLD_GEOMETRY_METRIC '));
const largestBytes = Math.max(...all.map(entity => Buffer.byteLength(JSON.stringify(entity), 'utf8')));
assert.equal(Number(/largest_entity_bytes=(\d+)/.exec(geometryMetric)[1]), largestBytes,
    'payload sizing counts serialized UTF-8 bytes, including non-ASCII ride names');
assert.equal(all.find(e => e.kind === 'ride').collision.volumes.length, 2,
    'ride retains separate track segments below one combat identity');
assert.equal(all.find(e => e.kind === 'ride').collision.volumes[0].base_z, 112);
const ground = sent.filter(m => m.kind === 'world.snapshot.chunk').flatMap(m => m.payload.terrain || []);
const terrainAt = (x, y) => ground.find(cell => cell.x === x && cell.y === y);
assert.equal(terrainAt(0, 0).height, 112);
assert.equal(terrainAt(0, 0).slope, 3, 'native surface slope is exported');
assert.equal(terrainAt(5, 2).path_layers[0].slope_direction, 0,
    'native sloped path direction is exported');
assert.equal(terrainAt(5, 2).path_layers[0].base_height, 112);
assert.equal(terrainAt(1, 0).water, 128);
assert.equal(terrainAt(1, 0).walkable, false);
assert.equal(all.length, 8);
const overheadScenery = all.find(e => e.type === 'rct2.scenery_small.no_supports');
assert.equal(overheadScenery.collision.volumes[0].base_z, 160,
    'scenery with no supports has an overhead physical lower bound');
assert.deepEqual(terrainAt(6, 6).path_layers.map(layer => layer.base_height), [112, 144],
    'snapshot preserves ground and elevated paths at one tile');
assert.ok(!all.some(e => e.geometry.cells.some(c => c.x === 7 && c.y === 7)),
    'ghost construction does not enter committed geometry');
assert.deepEqual([...new Set(all.map(e => e.kind))].sort(), ['large_scenery', 'path', 'ride', 'small_scenery', 'wall']);
const large = all.find(e => e.kind === 'large_scenery');
assert.equal(large.geometry.cells.length, 2, 'multi-tile object retains one identity');
assert.equal(large.geometry.rects[0].width, 64, 'adjacent cells merge into one collision rectangle');
assert.deepEqual(JSON.parse(JSON.stringify(all.find(e => e.kind === 'wall').geometry.rects[0])),
    { x: 160, y: 60, width: 32, height: 4 },
    'south-edge wall collision matches OpenRCT2 painting');
assert.equal(sent.filter(m => m.kind === 'world.snapshot.chunk').length, begin.payload.chunks);
const sid = begin.session;
socket.handlers.data(JSON.stringify({ v: 1, kind: 'combat.snapshot', session: sid,
    payload: { seq: 1, bw_tick: 3, units: [{ id: 'openbw:7', kind: 'zerg_zergling', owner: 0,
        x: 48, y: 48, facing: 0, motion: 'walk', hp: 35, max_hp: 35, attack_frames: 0 }] } }) + '\n');
assert.equal(applied.length, 1, 'combat actors use synchronized native action');
const snapshotAction = registered.get('rtsbridge.applySnapshot');
const validActor = { id: 'openbw:7', kind: 'zerg_zergling', owner: 0,
    x: 48, y: 48, facing: 0, motion: 'walk', hp: 35, max_hp: 35, attack_frames: 0 };
const validSnapshot = { session: sid, seq: 20, units: [validActor] };
assert.equal(snapshotAction.query({ player: 2, args: validSnapshot }).error, 1,
    'clients cannot author actor snapshots');
for (const units of [[validActor, validActor], [{ ...validActor, hp: -1 }],
    [{ ...validActor, x: 9999 }], [{ ...validActor, facing: 256 }],
    [{ ...validActor, motion: 'teleport' }]]) {
    assert.equal(snapshotAction.query({ player: 1, args: { ...validSnapshot, units } }).error, 1,
        'invalid actor arrays are rejected atomically');
}
const mission = { session: sid, scenario_id: 'example-defense', display_name: 'Example Defense',
    objective: 'Defend the carousel', wave_ordinal: 1, wave_total: 3,
    wave_state: 'spawning', outcome: '', error: '' };
socket.handlers.data(JSON.stringify({ v: 1, kind: 'scenario.status', session: sid, payload: mission }) + '\n');
const missionAction = registered.get('rtsbridge.scenarioStatus');
assert.ok(missionAction, 'mission action registered');
assert.equal(missionAction.query({ player: 2, args: mission }).error, 1, 'clients cannot author mission status');
assert.ok(actions.some(action => action.name === 'rtsbridge.scenarioStatus'
    && action.args.scenario_id === 'example-defense'), 'host synchronized mission status');
const many = Array.from({ length: 100 }, function (_, index) {
    const marine = index % 2 === 0;
    return { id: 'openbw:' + (1000 + index), kind: marine ? 'terran_marine' : 'zerg_zergling',
        owner: marine ? 1 : 0, x: 32 + (index % 10) * 16, y: 32 + Math.floor(index / 10) * 16,
        facing: 0, motion: 'idle', hp: marine ? 40 : 35,
        max_hp: marine ? 40 : 35, attack_frames: 0 };
});
socket.handlers.data(JSON.stringify({ v: 1, kind: 'combat.snapshot', session: sid,
    payload: { seq: 2, bw_tick: 6, units: many } }) + '\n');
assert.equal(applied.at(-1).units.length, 100, 'world actor transport accepts 100 mixed units');
const runtimeMarine = { ...many[0], id: 'openbw:3001' };
socket.handlers.data(JSON.stringify({ v: 1, kind: 'combat.snapshot', session: sid,
    payload: { seq: 3, bw_tick: 9, units: many.concat([runtimeMarine]) } }) + '\n');
assert.equal(applied.at(-1).units.length, 100, 'unbound runtime Marine is not rendered');
socket.handlers.data(JSON.stringify({ v: 1, kind: 'actor.bind', session: sid,
    payload: { id: runtimeMarine.id, generation: 1 } }) + '\n');
socket.handlers.data(JSON.stringify({ v: 1, kind: 'combat.snapshot', session: sid,
    payload: { seq: 4, bw_tick: 12, units: many.concat([runtimeMarine]) } }) + '\n');
assert.equal(applied.at(-1).units.length, 101, 'bound runtime Marine is rendered');
assert.ok(actions.some(a => a.name === 'rtsbridge.actorLifecycle' && a.args.state === 'active'));
assert.equal(registered.get('rtsbridge.marineCommand').query({ player: 1, args: {
    session: sid, request: 98, unit_ids: [runtimeMarine.id], verb: 'hold'
} }).error, undefined, 'bound runtime Marine is commandable');
selectionTool.onDown({ mapCoords: { x: runtimeMarine.x, y: runtimeMarine.y } });
selectionTool.onUp({ mapCoords: { x: runtimeMarine.x, y: runtimeMarine.y } });
assert.ok(logs.some(line => line.includes('selected Marines=openbw:3001')),
    'native hit testing selects the runtime Marine');
shortcuts.get('starcoaster.save-group-1').callback();
selectionTool.onDown({ mapCoords: { x: 0, y: 32 } });
selectionTool.onMove({ mapCoords: { x: 96, y: 0 }, isDown: true });
selectionTool.onUp({ mapCoords: { x: 96, y: 0 } });
assert.ok(logs.at(-1).includes('openbw:3001') && logs.at(-1).includes('openbw:1002'),
    'drag selection includes runtime and starting Marines');
selectionTool.onRightClick({ mapCoords: { x: 80, y: 80 } });
drain();
assert.ok(sent.filter(m => m.kind === 'combat.command').at(-1).payload.unit_ids.includes('openbw:3001'),
    'squad movement order includes the runtime Marine');
socket.handlers.data(JSON.stringify({ v: 1, kind: 'actor.despawn', session: sid,
    payload: { id: runtimeMarine.id, generation: 1 } }) + '\n');
const commandsBeforeRemoved = actions.filter(a => a.name === 'rtsbridge.marineCommand').length;
shortcuts.get('starcoaster.hold-position').callback();
const commandsAfterRemoved = actions.filter(a => a.name === 'rtsbridge.marineCommand');
assert.equal(commandsAfterRemoved.length, commandsBeforeRemoved + 1);
assert.ok(!commandsAfterRemoved.at(-1).args.unit_ids.includes(runtimeMarine.id),
    'removed actor is cleared from squad selection before the next snapshot');
shortcuts.get('starcoaster.recall-group-1').callback();
shortcuts.get('starcoaster.hold-position').callback();
assert.equal(actions.filter(a => a.name === 'rtsbridge.marineCommand').length, commandsAfterRemoved.length,
    'removed actor is cleared from the saved group');
socket.handlers.data(JSON.stringify({ v: 1, kind: 'combat.snapshot', session: sid,
    payload: { seq: 5, bw_tick: 15, units: many.concat([runtimeMarine]) } }) + '\n');
assert.equal(applied.at(-1).units.length, 100, 'despawned runtime Marine is removed');
const command = registered.get('rtsbridge.marineCommand');
assert.ok(command.query({ player: 1, args: { session: sid, request: 1,
    unit_ids: [runtimeMarine.id], verb: 'hold' } }).error,
    'despawned runtime Marine cannot be commanded');
assert.equal(command.query({ player: 1, args: { session: sid, request: 1,
    unit_ids: ['openbw:1000'], verb: 'attack', target_id: 'openbw:1001' } }).error, undefined);
command.execute({ player: 1, args: { session: sid, request: 1,
    unit_ids: ['openbw:1000'], verb: 'attack', target_id: 'openbw:1001' } });
drain();
assert.equal(sent.filter(m => m.kind === 'combat.command').at(-1).payload.target_id, 'openbw:1001');
const squad = ['openbw:1000', 'openbw:1002', 'openbw:1004', 'openbw:1006', 'openbw:1008', 'openbw:1010'];
const beforeSquad = sent.filter(m => m.kind === 'combat.command').length;
const squadArgs = { session: sid, request: 2, unit_ids: squad, verb: 'attack_move', x: 80, y: 80 };
assert.equal(command.query({ player: 1, args: squadArgs }).error, undefined);
command.execute({ player: 1, args: squadArgs });
drain();
const squadCommands = sent.filter(m => m.kind === 'combat.command');
assert.equal(squadCommands.length, beforeSquad + 1, 'squad order uses one command');
assert.deepEqual([...squadCommands.at(-1).payload.unit_ids], squad);
const rideTarget = all.find(e => e.kind === 'ride');
const wallTarget = all.find(e => e.kind === 'wall');
const sceneryTarget = all.find(e => e.kind === 'small_scenery');
socket.handlers.data(JSON.stringify({ v: 1, kind: 'world.ready', session: sid,
    payload: { entities: 8, targets: 3, target_ids: [rideTarget.id, wallTarget.id, sceneryTarget.id], navigation: 'native' } }) + '\n');
const spawnAction = registered.get('rtsbridge.spawnMarine');
const spawnArgs = { session: sid, request_id: sid + ':spawn:1:1', count: 5, x: 96, y: 96 };
assert.equal(spawnAction.query({ player: 1, args: spawnArgs }).error, undefined,
    'current commander may request reinforcements');
assert.ok(spawnAction.query({ player: 2, args: spawnArgs }).error,
    'another player cannot request Marine reinforcements');
assert.ok(spawnAction.query({ player: 1, args: { ...spawnArgs, count: 6 } }).error,
    'spawn action caps batches at five');
assert.ok(spawnAction.query({ player: 1, args: { ...spawnArgs, x: 9999 } }).error,
    'spawn action rejects locations outside the park');
squadWidgets.find(widget => widget.name === 'spawn-mode').onClick();
assert.equal(selectionTool.id, 'starcoaster.spawn-marine', 'spawn button activates park placement tool');
selectionTool.onMove({ mapCoords: { x: 96, y: 96 } });
assert.equal(sandbox.ui.tileSelection.tiles.length, 1, 'spawn placement is highlighted');
selectionTool.onDown({ mapCoords: { x: 96, y: 96 } });
drain();
const spawnRequest = sent.filter(message => message.kind === 'unit.spawn.request').at(-1);
assert.ok(spawnRequest && spawnRequest.payload.count === 5 && spawnRequest.payload.unit_type === 'terran_marine');
assert.equal(selectionTool.id, 'starcoaster.select-marine', 'placement restores Marine selection');
socket.handlers.data(JSON.stringify({ v: 1, kind: 'unit.spawn.status', session: sid,
    payload: { request_id: spawnRequest.payload.request_id, state: 'ready', units: [
        { index: 0, state: 'ready', actor_id: 'openbw:3001' },
        { index: 1, state: 'ready', actor_id: 'openbw:3002' } ] } }) + '\n');
assert.ok(actions.some(action => action.name === 'rtsbridge.spawnStatus' && action.args.state === 'ready'),
    'spawn progress is synchronized to clients');
const requestsBeforeCancel = sent.filter(message => message.kind === 'unit.spawn.request').length;
squadWidgets.find(widget => widget.name === 'spawn-mode').onClick();
selectionTool.onFinish();
assert.equal(sent.filter(message => message.kind === 'unit.spawn.request').length, requestsBeforeCancel,
    'canceling placement does not issue a spawn request');
squadWidgets.find(widget => widget.name === 'select-mode').onClick();
assert.equal(selectionTool.id, 'starcoaster.select-marine', 'selection remains available after cancel');
assert.ok(actions.filter(a => a.name === 'rtsbridge.targetCatalog').at(-1).args.targets
    .some(target => target.id === rideTarget.id));
const structureArgs = { session: sid, request: 3, unit_ids: ['openbw:1000'],
    verb: 'attack', target_entity_id: rideTarget.id };
assert.equal(command.query({ player: 1, args: structureArgs }).error, undefined);
command.execute({ player: 1, args: structureArgs });
drain();
assert.equal(sent.filter(m => m.kind === 'combat.command').at(-1).payload.target_id, rideTarget.id);
const catalogAction = registered.get('rtsbridge.targetCatalog');
function catalog(version, targets, count) {
    const parts = [];
    for (let index = 0; index < targets.length; index += 128) parts.push(targets.slice(index, index + 128));
    if (!parts.length) parts.push([]);
    const chunks = count || parts.length;
    return parts.map((items, index) => ({ session: sid, version, index, chunks, targets: items }));
}
function applyCatalog(args) {
    const result = catalogAction.query({ player: 1, args });
    assert.equal(result.error, undefined, result.errorMessage);
    catalogAction.execute({ player: 1, args });
}
function canAttack(targetId) {
    return !command.query({ player: 1, args: { session: sid, request: 99,
        unit_ids: ['openbw:1000'], verb: 'attack', target_entity_id: targetId } }).error;
}
let previousTarget = rideTarget.id;
for (const [version, size] of [[3, 32], [4, 128], [5, 197], [6, 512]]) {
    const targets = Array.from({ length: size }, (_, index) => ({
        id: `openrct2:wall:boundary_${version}_${index}#1`,
        rects: [{ x: 0, y: 0, width: 4, height: 4 }]
    }));
    const parts = catalog(version, targets);
    applyCatalog(parts[0]);
    if (parts.length > 1) {
        assert.ok(canAttack(previousTarget), 'incomplete catalog preserves the active catalog');
        assert.ok(!canAttack(targets[0].id), 'incomplete catalog is not visible');
        assert.ok(catalogAction.query({ player: 1, args: parts[0] }).error,
            'duplicate chunk is rejected');
    }
    parts.slice(1).forEach(applyCatalog);
    assert.ok(canAttack(targets[0].id), `first of ${size} targets is active`);
    assert.ok(canAttack(targets.at(-1).id), `last of ${size} targets is active`);
    assert.ok(!canAttack(previousTarget), 'completed catalog replaces old targets');
    previousTarget = targets[0].id;
    assert.ok(catalogAction.query({ player: 1, args: parts.at(-1) }).error,
        'completed catalog rejects stale chunks');
}
const dropped = catalog(7, Array.from({ length: 129 }, (_, index) => ({
    id: `openrct2:wall:dropped_${index}#1`, rects: [{ x: 0, y: 0, width: 4, height: 4 }]
})));
applyCatalog(dropped[0]);
assert.ok(canAttack(previousTarget), 'a dropped final chunk preserves the completed catalog');
assert.ok(!canAttack(dropped[0].targets[0].id), 'a dropped chunk exposes no staged target');
assert.ok(catalogAction.query({ player: 1, args: { ...dropped[1], chunks: 3 } }).error,
    'conflicting chunk count is rejected');
assert.ok(catalogAction.query({ player: 1, args: { ...dropped[1], targets: [dropped[0].targets[0]] } }).error,
    'duplicate target across chunks is rejected');
applyCatalog(catalog(8, [
    { id: rideTarget.id, rects: rideTarget.geometry.rects },
    { id: wallTarget.id, rects: wallTarget.geometry.rects },
    { id: sceneryTarget.id, rects: sceneryTarget.geometry.rects }
])[0]);
const beforeJoin = actions.filter(a => a.name === 'rtsbridge.targetCatalog').length;
subscriptions.get('network.join')({ player: 2 });
const joinChunks = actions.filter(a => a.name === 'rtsbridge.targetCatalog').slice(beforeJoin);
assert.equal(joinChunks.flatMap(a => a.args.targets).length, 3,
    'late join replays the complete current catalog');
sandbox.network.players.push({ id: 2 });
const clientReady = registered.get('rtsbridge.clientReady');
assert.equal(clientReady.query({ player: 2, args: { session: sid } }).error, undefined);
const beforeReady = actions.filter(a => a.name === 'rtsbridge.targetCatalog').length;
clientReady.execute({ player: 2, args: { session: sid } });
subscriptions.get('interval.tick')();
assert.ok(actions.filter(a => a.name === 'rtsbridge.targetCatalog').length > beforeReady,
    'client readiness replays the current catalog after plugin startup');
assert.ok(actions.filter(action => action.name === 'rtsbridge.scenarioStatus'
    && action.args.scenario_id === 'example-defense').length >= 2,
    'late client receives the current authoritative mission status');
assert.match(command.query({ player: 2, args: squadArgs }).errorMessage, /commander/);
socket.handlers.data(JSON.stringify({ v: 1, kind: 'world.outcome', session: sid,
    payload: { scenario_id: 'frontier-outpost', state: 'victory', objective_id: 'openrct2:ride:17#1' } }) + '\n');
assert.equal(actions.filter(a => a.name === 'rtsbridge.worldOutcome').length, 1,
    'authoritative outcome uses a replicated OpenRCT2 action');
assert.match(command.query({ player: 1, args: squadArgs }).errorMessage, /ended/);
const rideEntity = all.find(e => e.kind === 'ride');
const event = { id: 'death:1', entity_id: rideEntity.id, proxy_id: 'openbw:8', type: 'destruction', health: 0 };
socket.handlers.data(JSON.stringify({ v: 1, kind: 'combat.event', session: sid, payload: event }) + '\n');
drain();
assert.equal(actions.filter(a => a.name === 'ridedemolish').length, 1);
assert.equal(sent.find(m => m.kind === 'combat.result').payload.state, 'removal_confirmed');
assert.equal(sent.find(m => m.kind === 'combat.result').revision, 2);
assert.ok(at(4, 1).some(element => element.type === 'small_scenery'));
assert.ok(at(5, 1).some(element => element.type === 'wall'));
assert.ok(at(5, 2).some(element => element.type === 'footpath'));
socket.handlers.data(JSON.stringify({ v: 1, kind: 'combat.event', session: sid,
    payload: { id: 'death:wall', entity_id: wallTarget.id, proxy_id: 'openbw:10',
        type: 'destruction', health: 0 } }) + '\n');
drain();
socket.handlers.data(JSON.stringify({ v: 1, kind: 'entity.remove', session: sid,
    payload: { id: wallTarget.id } }) + '\n');
const survivors = actions.filter(a => a.name === 'rtsbridge.targetCatalog').at(-1).args.targets;
assert.ok(survivors.some(target => target.id === sceneryTarget.id),
    'rediscovery during demolition retains other active targets');
assert.ok(!survivors.some(target => target.id === wallTarget.id),
    'demolished wall leaves the target catalog');
socket.handlers.data(JSON.stringify({ v: 1, kind: 'combat.event', session: sid, payload: event }) + '\n');
assert.equal(actions.filter(a => a.name === 'ridedemolish').length, 1, 'duplicate death cannot demolish twice');
ride = { id: 17, name: 'A New Carousel', type: 33, classification: 'ride',
    object: { identifier: 'rct2.ride.mgr1' }, status: 'closed', isEmpty: true };
at(1, 1).push({ type: 'track', ride: 17, baseHeight: 14 });
socket.handlers.data(JSON.stringify({ v: 1, kind: 'world.resync', session: sid, payload: {} }) + '\n');
drain();
const rebuilt = sent.filter(m => m.kind === 'world.snapshot.chunk').flatMap(m => m.payload.entities || [])
    .filter(e => e.source_id === 'ride:17').at(-1);
assert.notEqual(rebuilt.id, rideEntity.id, 'rebuilt object receives a new generation');
rejectNextRideDemolition = true;
socket.handlers.data(JSON.stringify({ v: 1, kind: 'combat.event', session: sid,
    payload: { id: 'death:rebuilt', entity_id: rebuilt.id, proxy_id: 'openbw:11',
        type: 'destruction', health: 0 } }) + '\n');
drain();
assert.ok(ride, 'rejected native demolition leaves the ride intact');
assert.equal(sent.filter(m => m.kind === 'combat.result').at(-1).payload.state, 'removal_failed');
const oldScenery = all.find(e => e.kind === 'small_scenery');
subscriptions.get('action.execute')({ action: 'smallsceneryremove',
    args: { x: 4 * 32, y: 1 * 32, z: 112 }, result: { error: 0 } });
socket.handlers.data(JSON.stringify({ v: 1, kind: 'combat.event', session: sid,
    payload: { id: 'death:2', entity_id: oldScenery.id, proxy_id: 'openbw:9',
        type: 'destruction', health: 0 } }) + '\n');
drain();
assert.equal(sent.filter(m => m.kind === 'combat.result').at(-1).payload.state, 'removal_failed',
    'a replacement at the same tile cannot inherit an older combat death');
assert.equal(actions.filter(a => a.name === 'smallsceneryremove').length, 0);
assert.ok(logs.some(line => line.startsWith('WORLD_REMOVAL')));
function construction(action, args, result = { error: 0 }) {
    subscriptions.get('action.execute')({ action, args, result, isClientOnly: false });
}
function ticks(count = 6) {
    for (let index = 0; index < count; index++) subscriptions.get('interval.tick')();
}
function lastChange() {
    return JSON.parse(logs.filter(line => line.startsWith('WORLD_CHANGESET ')).at(-1).slice(16));
}
const firstRideId = rebuilt.id;
const changeCount = () => logs.filter(line => line.startsWith('WORLD_CHANGESET ')).length;
ticks(); // Flush the earlier simulated removal action before checking repeat scans.
const noChangeCount = changeCount();
construction('wallplace', { x: 7 * 32, y: 7 * 32, z: 112 });
ticks();
assert.equal(changeCount(), noChangeCount, 'ghost preview does not produce a committed patch');
ticks(1200);
assert.equal(changeCount(), noChangeCount, 'repeat discovery does not change generations');
ride.name = 'Renamed without geometry changes';
ticks(1200);
assert.equal(changeCount(), noChangeCount, 'display name does not produce a geometry delta');
const raisedTrack = at(1, 1).find(element => element.type === 'track');
raisedTrack.baseHeight = 18; raisedTrack.baseZ = 144;
construction('trackplace', { ride: 17, x: 32, y: 32, z: 144 });
ticks();
assert.ok(lastChange().modifications.includes(firstRideId),
    'height-only track edit modifies the same ride identity');
at(2, 1).push({ type: 'track', ride: 17, baseHeight: 14 });
construction('trackplace', { ride: 17, x: 64, y: 32, z: 112 });
ticks();
assert.ok(lastChange().modifications.includes(firstRideId), 'track placement modifies the existing ride');
assert.ok(!lastChange().additions.some(id => id.startsWith('openrct2:ride:17#')),
    'track placement preserves ride generation');
at(2, 1).pop();
construction('trackremove', { x: 64, y: 32, z: 112 });
ticks();
assert.ok(!lastChange().removals.includes(firstRideId), 'track removal preserves the ride generation');
at(3, 1).push({ type: 'track', ride: 17, baseHeight: 14 });
construction('trackplace', { ride: 17, x: 96, y: 32, z: 112 });
ticks();
assert.ok(lastChange().modifications.includes(firstRideId), 'subsequent track edit retains the ride ID');
at(6, 3).push({ type: 'wall', object: 3, baseHeight: 14, direction: 0 });
at(7, 3).push({ type: 'footpath', object: 4, surfaceObject: 4,
    baseHeight: 14, baseZ: 112 });
construction('wallplace', { x: 192, y: 96, z: 112 });
construction('footpathplace', { x: 224, y: 96, z: 112 });
ticks();
assert.equal(lastChange().additions.filter(id => id.includes('wall:') || id.includes('footpath:')).length,
    2, 'independent changes share a batch');
assert.ok(lastChange().base_revision >= 2);
at(6, 3).pop();
construction('wallremove', { x: 192, y: 96, z: 112 });
ticks();
assert.ok(lastChange().additions.some(id => id.includes('footpath:'))
    && !lastChange().additions.some(id => id.includes('wall:')),
    'an edit reverted before publishing is coalesced');
at(0, 1)[0].waterHeight = 128;
construction('waterraise', { x: 0, y: 32 });
ticks();
assert.ok(lastChange().terrain >= 1, 'terrain replacement appears in the batch');
const beforeRecreate = firstRideId;
ride = null;
for (const elements of tiles.values()) for (let index = elements.length - 1; index >= 0; index--)
    if (elements[index].type === 'track') elements.splice(index, 1);
construction('ridedemolish', { ride: 17, modifyType: 0 });
ride = { id: 17, name: 'Recreated Carousel', type: 33, classification: 'ride',
    object: { identifier: 'rct2.ride.mgr1' }, status: 'closed', isEmpty: true };
at(1, 1).push({ type: 'track', ride: 17, baseHeight: 14 });
construction('ridecreate', {}, { error: 0, ride: 17 });
ticks();
assert.ok(lastChange().removals.includes(beforeRecreate), 'demolished ride is removed');
assert.ok(lastChange().additions.some(id => id.startsWith('openrct2:ride:17#') && id !== beforeRecreate),
    'recreated ride receives a new generation');
socket.handlers.data(JSON.stringify({ v: 1, kind: 'world.resync', session: sid, payload: {} }) + '\n');
at(6, 4).push({ type: 'wall', object: 3, baseHeight: 14, direction: 0 });
construction('wallplace', { x: 192, y: 128, z: 112 });
drain();
ticks();
assert.ok(lastChange().additions.some(id => id.includes('wall:3:192:128:112')),
    'an edit during snapshot transmission is retained for the next batch');
console.log('world plugin discovery and lifecycle validation passed');
