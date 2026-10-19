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
let selectionTool, activeTool = null;
const actorScreens = new Map();
let squadWidgets;
const openedWindows = [];
const starcraftBuildings = ['terran_barracks', 'terran_academy', 'terran_supply_depot',
    'terran_factory', 'terran_armory', 'zerg_hatchery', 'zerg_spawning_pool'];
let socket;
const sandbox = {
    map: { size: { x: 8, y: 8 }, get rides() { return ride ? [ride] : []; },
        getRide(id) { return ride && id === ride.id ? ride : null; },
        getTile(x, y) { const elements = at(x, y); return { numElements: elements.length,
            getElement(index) { return elements[index]; } }; } },
    objectManager: { getAllObjects(kind) {
        if (kind === 'large_scenery') return [{ index: 1, identifier: 'rct2.scenery_large.test',
            tiles: [{ offset: { x: 0, y: 0, z: 0 } }, { offset: { x: 32, y: 0, z: 0 } }] }]
            .concat(starcraftBuildings.map((name, index) => ({ index: 100 + index,
                identifier: 'starcoaster.scenery_large.' + name,
                tiles: [{ offset: { x: 0, y: 0, z: 0 } }] })));
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
    rtsBridge: { version: 5, assetVersion: 4, cursorWorld() { return null; }, invalidateAnimation() {}, setBuildingAnimations() {}, applySnapshot(snapshot) { applied.push(snapshot); },
        actorScreenPosition(id) { return actorScreens.get(id) || null; },
        hitTest(x, y) { return x === 32 && y === 32 ? 'openbw:3001' : null; } },
    ui: { tileSelection: { tiles: [] }, get tool() { return activeTool; }, openWindow(desc) { squadWidgets = desc.widgets;
            openedWindows.push(desc);
            const camera = { zoom: 1, rotation: 0, moveTo(position) { this.centre = position; } };
            return { findWidget(name) { const widget = desc.widgets.find(item => item.name === name);
                    if (widget && name === 'building-camera') widget.viewport = camera;
                    return widget; }, close() { if (desc.onClose) desc.onClose(); } }; },
        registerShortcut(shortcut) { shortcuts.set(shortcut.id, shortcut); },
        registerViewportInteraction(handler) { selectionTool = handler; },
        activateTool(tool) { if (activeTool) activeTool.cancel(); activeTool = tool;
            tool.cancel = function () { activeTool = null; if (tool.onFinish) tool.onFinish(); }; }, showError() {} },
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
assert.equal(activeTool, null, 'passive selection leaves normal park interaction active');
assert.equal(selectionTool.id, 'starcoaster.select-marine');
activeTool = { id: 'construction', cancel() { activeTool = null; } };
subscriptions.get('interval.tick')();
assert.equal(activeTool.id, 'construction', 'construction keeps its active tool');
activeTool = null;
subscriptions.get('interval.tick')();
assert.equal(activeTool, null, 'finishing construction restores native park interaction');
const parkEvent = { mapCoords: { x: 32, y: 32 }, screenCoords: { x: 900, y: 900 } };
assert.equal(selectionTool.onHover(parkEvent), false);
selectionTool.onDown(parkEvent);
assert.equal(selectionTool.onUp(parkEvent), false, 'park clicks pass through');
assert.equal(selectionTool.onRightClick(parkEvent), false, 'right click without a squad passes through');
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
assert.ok(all.find(e => e.kind === 'ride').collision.volumes.every(volume =>
    volume.source.endsWith(':unrepresented_supports')),
    'straight rail diagnostics retain the missing-support reason');
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
for (const unit of many) actorScreens.set(unit.id, { x: unit.x, y: unit.y });
selectionTool.onDown({ mapCoords: { x: 200, y: 200 }, screenCoords: { x: 20, y: 20 } });
selectionTool.onUp({ mapCoords: { x: 0, y: 0 }, screenCoords: { x: 80, y: 60 } });
assert.ok(logs.at(-1).includes('openbw:1000') && logs.at(-1).includes('openbw:1002'),
    'starting Marines can be box selected before any reinforcements spawn');
const runtimeMarine = { ...many[0], id: 'openbw:3001' };
for (const unit of many.concat([runtimeMarine])) actorScreens.set(unit.id, { x: unit.x, y: unit.y });
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
actorScreens.set(runtimeMarine.id, { x: 190, y: 190, scale: 1 });
selectionTool.onDown({ mapCoords: { x: runtimeMarine.x, y: runtimeMarine.y }, screenCoords: { x: 190, y: 178 } });
assert.equal(selectionTool.onUp({ mapCoords: { x: 99, y: 99 }, screenCoords: { x: 190, y: 178 } }), true, 'screen hit consumes click despite different terrain projection');
assert.ok(logs.some(line => line.includes('selected units=openbw:3001')),
    'native hit testing selects the runtime Marine');
assert.equal(selectionTool.onHover({ screenCoords: { x: 190, y: 178 } }), true);
assert.equal(selectionTool.onHover({ screenCoords: { x: 190, y: 178 }, alt: true }), false);
selectionTool.onDown({ screenCoords: { x: 190, y: 178 }, alt: true });
assert.equal(selectionTool.onUp({ screenCoords: { x: 190, y: 178 }, alt: true }), false,
    'Alt lets the native object underneath a Marine receive the click');
actorScreens.set(runtimeMarine.id, { x: 190, y: 190, scale: 0.25 });
assert.equal(selectionTool.onHover({ screenCoords: { x: 190, y: 185 } }), true);
assert.equal(selectionTool.onHover({ screenCoords: { x: 200, y: 185 } }), false,
    'zoomed-out footprint does not steal a nearby park object');
actorScreens.set(runtimeMarine.id, { x: 190, y: 190, scale: 2 });
assert.equal(selectionTool.onHover({ screenCoords: { x: 210, y: 150 } }), true,
    'zoomed-in body remains selectable above its terrain tile');
selectionTool.onDown({ screenCoords: { x: 190, y: 178 } });
selectionTool.onFinish();
assert.equal(selectionTool.onUp({ screenCoords: { x: 190, y: 178 } }), false,
    'release over another window cancels the gesture');
const parkCommands = sent.filter(m => m.kind === 'combat.command').length;
assert.equal(selectionTool.onRightClick({ ...parkEvent, alt: true }), false);
assert.equal(sent.filter(m => m.kind === 'combat.command').length, parkCommands);
actorScreens.set(runtimeMarine.id, { x: runtimeMarine.x, y: runtimeMarine.y });
shortcuts.get('starcoaster.save-group-1').callback();
selectionTool.onDown({ mapCoords: { x: 0, y: 32 }, screenCoords: { x: 0, y: 0 } });
selectionTool.onMove({ mapCoords: { x: 96, y: 0 }, screenCoords: { x: 96, y: 32 }, isDown: true });
selectionTool.onUp({ mapCoords: { x: 96, y: 0 }, screenCoords: { x: 96, y: 32 } });
assert.ok(logs.at(-1).includes('openbw:3001') && logs.at(-1).includes('openbw:1002'),
    'drag selection includes runtime and starting Marines');
selectionTool.onRightClick({ mapCoords: { x: 80, y: 80 } });
drain();
assert.ok(sent.filter(m => m.kind === 'combat.command').at(-1).payload.unit_ids.includes('openbw:3001'),
    'squad movement order includes the runtime Marine');
activeTool = { id: 'construction', cancel() { activeTool = null; } };
sandbox.ui.tileSelection.tiles = [{ x: 224, y: 224 }];
subscriptions.get('interval.tick')();
assert.equal(activeTool.id, 'construction');
assert.deepEqual(sandbox.ui.tileSelection.tiles, [{ x: 224, y: 224 }], 'construction owns its highlights');
activeTool = null;
subscriptions.get('interval.tick')();
const beforeRestoredOrder = sent.filter(m => m.kind === 'combat.command').length;
assert.ok(sandbox.ui.tileSelection.tiles.length > 0, 'unit highlights return after construction');
selectionTool.onRightClick({ mapCoords: { x: 112, y: 112 } });
drain();
assert.equal(sent.filter(m => m.kind === 'combat.command').length, beforeRestoredOrder + 1,
    'restored selection tool delivers a replacement move order');
assert.equal(sent.filter(m => m.kind === 'combat.command').at(-1).payload.x, 112);
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
const deadRuntimeMarine = { ...runtimeMarine, hp: 0, alive: false, motion: 'death' };
socket.handlers.data(JSON.stringify({ v: 1, kind: 'combat.snapshot', session: sid,
    payload: { seq: 6, bw_tick: 18, units: many.concat([deadRuntimeMarine]) } }) + '\n');
assert.equal(applied.at(-1).units.length, 101,
    'a despawned runtime actor retains its terminal visual frame');
assert.equal(applied.at(-1).units.at(-1).motion, 'death');
const command = registered.get('rtsbridge.marineCommand');
assert.ok(command.query({ player: 1, args: { session: sid, request: 1,
    unit_ids: [runtimeMarine.id], verb: 'hold' } }).error,
    'despawned runtime Marine cannot be commanded');
assert.equal(command.query({ player: 1, args: { session: sid, request: 10001,
    unit_ids: ['openbw:1000'], verb: 'attack', target_id: 'openbw:1001' } }).error, undefined);
command.execute({ player: 1, args: { session: sid, request: 10001,
    unit_ids: ['openbw:1000'], verb: 'attack', target_id: 'openbw:1001' } });
drain();
assert.equal(sent.filter(m => m.kind === 'combat.command').at(-1).payload.target_id, 'openbw:1001');
const squad = ['openbw:1000', 'openbw:1002', 'openbw:1004', 'openbw:1006', 'openbw:1008', 'openbw:1010'];
const beforeSquad = sent.filter(m => m.kind === 'combat.command').length;
const squadArgs = { session: sid, request: 10002, unit_ids: squad, verb: 'attack_move', x: 80, y: 80 };
assert.equal(command.query({ player: 1, args: squadArgs }).error, undefined);
command.execute({ player: 1, args: squadArgs });
drain();
const squadCommands = sent.filter(m => m.kind === 'combat.command');
assert.equal(squadCommands.length, beforeSquad + 1, 'squad order uses one command');
assert.deepEqual([...squadCommands.at(-1).payload.unit_ids], squad);
for (const [rotation, zoom, elevation] of [[0, 0, 0], [1, 1, 64], [2, 2, 128], [3, -1, 32]]) {
    for (const unit of many) actorScreens.set(unit.id, { x: 500, y: 500 });
    actorScreens.set('openbw:1000', { x: 30 + rotation, y: 40 + zoom });
    actorScreens.set('openbw:1002', { x: 60 + rotation, y: 35 - elevation / 16 });
    selectionTool.onDown({ mapCoords: { x: 220, y: 220 }, screenCoords: { x: 20, y: 20 } });
    selectionTool.onUp({ mapCoords: { x: 0, y: 0 }, screenCoords: { x: 80, y: 60 } });
    const chosen = logs.at(-1);
    assert.ok(chosen.includes('openbw:1000') && chosen.includes('openbw:1002')
        && !chosen.includes('openbw:1004'), `screen selection rotation=${rotation} zoom=${zoom} z=${elevation}`);
}
for (const unit of many) actorScreens.set(unit.id, { x: 40 + unit.x / 8, y: 40 + unit.y / 8 });
selectionTool.onDown({ mapCoords: { x: 255, y: 255 }, screenCoords: { x: 20, y: 20 } });
selectionTool.onUp({ mapCoords: { x: 0, y: 0 }, screenCoords: { x: 120, y: 120 } });
const beforeLargeOrder = sent.filter(m => m.kind === 'combat.command').length;
selectionTool.onRightClick({ mapCoords: { x: 200, y: 200 } });
drain();
const largeOrders = sent.filter(m => m.kind === 'combat.command').slice(beforeLargeOrder);
assert.deepEqual(largeOrders.map(m => m.payload.unit_ids.length), [32, 18],
    'all 50 selected Marines receive orders in supported batches');
const beforeRedirect = sent.filter(m => m.kind === 'combat.command').length;
selectionTool.onRightClick({ mapCoords: { x: 180, y: 180 } });
selectionTool.onRightClick({ mapCoords: { x: 80, y: 80 } });
drain();
const redirects = sent.filter(m => m.kind === 'combat.command').slice(beforeRedirect);
assert.deepEqual(redirects.map(m => m.payload.x), [180, 180, 80, 80],
    'replacement destinations retain command order across squad batches');
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
assert.equal(activeTool.id, 'starcoaster.spawn-marine', 'spawn button activates park placement tool');
activeTool.onMove({ mapCoords: { x: 96, y: 96 } });
assert.equal(sandbox.ui.tileSelection.tiles.length, 1, 'spawn placement is highlighted');
activeTool.onDown({ mapCoords: { x: 96, y: 96 } });
drain();
const spawnRequest = sent.filter(message => message.kind === 'unit.spawn.request').at(-1);
assert.ok(spawnRequest && spawnRequest.payload.count === 5 && spawnRequest.payload.unit_type === 'terran_marine');
assert.equal(activeTool, null, 'placement restores park interaction and passive selection');
socket.handlers.data(JSON.stringify({ v: 1, kind: 'unit.spawn.status', session: sid,
    payload: { request_id: spawnRequest.payload.request_id, state: 'ready', units: [
        { index: 0, state: 'ready', actor_id: 'openbw:3001' },
        { index: 1, state: 'ready', actor_id: 'openbw:3002' } ] } }) + '\n');
assert.ok(actions.some(action => action.name === 'rtsbridge.spawnStatus' && action.args.state === 'ready'),
    'spawn progress is synchronized to clients');
const requestsBeforeCancel = sent.filter(message => message.kind === 'unit.spawn.request').length;
squadWidgets.find(widget => widget.name === 'spawn-mode').onClick();
activeTool.cancel();
subscriptions.get('interval.tick')();
assert.equal(sent.filter(message => message.kind === 'unit.spawn.request').length, requestsBeforeCancel,
    'canceling placement does not issue a spawn request');
assert.equal(activeTool, null, 'spawn cancellation restores park interaction');
assert.ok(actions.filter(a => a.name === 'rtsbridge.targetCatalog').at(-1).args.targets
    .some(target => target.id === rideTarget.id));
const structureArgs = { session: sid, request: 10003, unit_ids: ['openbw:1000'],
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
assert.equal(clientReady.query({ player: 2, args: { session: '' } }).error, undefined,
    'a late client can request its first actor snapshot before knowing the session');
const beforeBootstrap = actions.filter(a => a.name === 'rtsbridge.applySnapshot').length;
const latestBeforeBootstrap = actions.filter(a => a.name === 'rtsbridge.applySnapshot').at(-1).args;
clientReady.execute({ player: 2, args: { session: '' } });
subscriptions.get('interval.tick')();
const bootstrap = actions.filter(a => a.name === 'rtsbridge.applySnapshot').slice(beforeBootstrap);
assert.equal(bootstrap.length, 1, 'late readiness replays the latest authoritative actor snapshot');
assert.equal(bootstrap[0].args.session, sid);
assert.equal(bootstrap[0].args.seq, latestBeforeBootstrap.seq);
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
const waveAction = registered.get('rtsbridge.requestWave');
const parkStatus = { session: sid, scenario_id: 'mt-zergling', display_name: 'Mt. Zergling',
    mode: 'park_defense', objective: 'Manage and defend the park', wave_ordinal: 0, wave_total: 0,
    wave_state: 'pending', outcome: '', error: '', total_triggered: 0, next_wave_seconds: 120,
    active_zerglings: 0, manual_cooldown_seconds: 0, manual_eligible: true };
assert.equal(missionAction.query({ player: 1, args: parkStatus }).error, undefined);
missionAction.execute({ player: 1, args: parkStatus });
missionAction.execute({ player: 1, args: { ...parkStatus, error: 'spawn_zones_temporarily_blocked' } });
subscriptions.get('interval.tick')();
assert.equal(squadWidgets.find(widget => widget.name === 'wave-feedback').text,
    'Spawn edges occupied; retrying', 'temporarily blocked waves show a retry message');
missionAction.execute({ player: 1, args: parkStatus });
const waveArgs = { session: sid, request: 1, request_id: `${sid}:wave:1:1` };
assert.equal(waveAction.query({ player: 1, args: waveArgs }).error, undefined);
assert.match(waveAction.query({ player: 2, args: { ...waveArgs, request_id: `${sid}:wave:2:1` } }).errorMessage,
    /commander/, 'only the authorized commander can request an extra wave');
assert.ok(waveAction.query({ player: 1, args: { ...waveArgs, session: 'stale' } }).error,
    'stale wave request is rejected');
const waveButton = squadWidgets.find(widget => widget.name === 'spawn-wave');
assert.equal(waveButton.text, 'Spawn Wave');
waveButton.onClick();
drain();
const buttonWave = sent.filter(message => message.kind === 'scenario.wave.request').at(-1);
assert.ok(buttonWave && buttonWave.payload.request_id.startsWith(`${sid}:wave:1:`),
    'button routes a wave through the server bridge');
assert.ok(Number(buttonWave.payload.request_id.split(':').at(-1)) > 1_000_000_000_000,
    'new plugin instances start request IDs beyond prior reconnect journals');
const waveStatus = registered.get('rtsbridge.waveStatus');
assert.ok(waveStatus.query({ player: 2, args: { session: sid, request_id: buttonWave.payload.request_id,
    accepted: true, wave_id: 'manual-0001', state: 'queued', reason: '' } }).error,
    'client cannot forge wave feedback');
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
const hudTargets = starcraftBuildings.map((type, index) => ({
    id: 'scenario:hud-' + type.replace(/_/g, '-'), type,
    rects: [{ x: index * 32, y: 7 * 32, width: 32, height: 32 }], health: 500
}));
applyCatalog(catalog(100, hudTargets)[0]);
const buildingState = registered.get('rtsbridge.buildingState');
const hudStates = [];
for (const [index, type] of starcraftBuildings.entries()) {
    at(index, 7).push({ type: 'large_scenery', object: 100 + index,
        baseHeight: 14, baseZ: 112, direction: 0 });
    const commands = type === 'terran_barracks' ? ['terran_marine', 'terran_firebat', 'terran_medic']
        : type === 'terran_factory' ? ['terran_vulture', 'terran_goliath']
            : type === 'zerg_hatchery' ? ['zerg_zergling'] : [];
    const availability = Object.fromEntries(commands.map(unit => [unit,
        { ready: true, reason: 'ready', requirement: '' }]));
    const state = { session: sid, id: hudTargets[index].id, native_id: 'openbw:' + (100 + index),
        owner: type.startsWith('zerg_') ? 0 : 1, race: type.startsWith('zerg_') ? 'Zerg' : 'Terran',
        completed: true, health: 500, max_health: 500, queue: 0, remaining_frames: 0,
        minerals: 500, gas: 250, supply_used: 0, supply_total: 18, larva_count: 0,
        command_authorized: !type.startsWith('zerg_'),
        availability, commands: commands.map((unit, slot) => ({ slot, action: 'unit.train',
            unit_type: unit, label: unit === 'zerg_zergling' ? 'Zerg_Zergling'
                : unit.replace('_', ' '), ready: true,
            reason: 'ready', requirement: '' })) };
    hudStates.push(state);
    assert.equal(buildingState.query({ player: 1, args: state }).error, undefined);
    buildingState.execute({ player: 1, args: state });
    const event = { screenCoords: { x: 16, y: 16 },
        mapCoords: { x: index * 32 + 16, y: 7 * 32 + 16 } };
    selectionTool.onDown(event);
    selectionTool.onUp(event);
    const window = openedWindows.at(-1);
    assert.equal(window.classification, 'starcoaster-building-info');
    assert.equal(window.widgets.filter(widget => widget.name.startsWith('building-command-')).length, 9);
    assert.equal(window.widgets.filter(widget => widget.type === 'viewport').length, 1);
    window.onUpdate();
    const card = window.widgets.filter(widget => widget.name.startsWith('building-command-'));
    const labels = window.widgets.filter(widget => widget.name.startsWith('building-label-'));
    assert.equal(labels.length, 9);
    assert.equal(card.filter(widget => !widget.isDisabled).length,
        type.startsWith('zerg_') ? 0 : commands.length);
    const emptyImage = card[8].image;
    assert.equal(card.filter(widget => widget.image === emptyImage && widget.isDisabled).length,
        9 - commands.length);
    assert.ok(card.slice(0, commands.length).every(widget => widget.image !== emptyImage),
        'native command icons remain intact after HUD updates');
    assert.ok(labels.slice(0, commands.length).every(widget => widget.text),
        'native command slots have short labels');
    assert.ok(labels.slice(0, commands.length).every(widget =>
        !/^(Terran|Zerg|Protoss)[ _]/.test(widget.text)),
    'command labels omit the faction prefix');
    assert.deepEqual(JSON.parse(JSON.stringify(window.widgets.find(widget => widget.name === 'building-camera').viewport.centre)),
        { x: index * 32 + 16, y: 7 * 32 + 16, z: 122 });
}
const scenarioHatchery = { ...hudStates[5], command_authorized: true };
assert.equal(buildingState.query({ player: 1, args: scenarioHatchery }).error, undefined);
buildingState.execute({ player: 1, args: scenarioHatchery });
const hatcheryEvent = { screenCoords: { x: 16, y: 16 },
    mapCoords: { x: 5 * 32 + 16, y: 7 * 32 + 16 } };
selectionTool.onDown(hatcheryEvent);
selectionTool.onUp(hatcheryEvent);
const authorizedHatcheryWindow = openedWindows.at(-1);
authorizedHatcheryWindow.onUpdate();
const zergButton = authorizedHatcheryWindow.widgets.find(
    widget => widget.name === 'building-command-0');
assert.equal(zergButton.isDisabled, false);
const priorActions = actions.length;
zergButton.onClick();
assert.equal(actions.length, priorActions + 1);
assert.equal(actions.at(-1).name, 'rtsbridge.marineCommand');
assert.equal(actions.at(-1).args.unit_type, 'zerg_zergling');
assert.equal(actions.at(-1).args.target_entity_id, hudTargets[5].id);
const scenarioTrainResult = { player: 1, request: actions.at(-1).args.request,
    unit: hudTargets[5].id, accepted: true, reason: 'ok' };
assert.equal(registered.get('rtsbridge.commandResult').query({
    player: 1, args: scenarioTrainResult }).error, undefined);
registered.get('rtsbridge.commandResult').execute({ player: 1, args: {
    player: 1, request: actions.at(-1).args.request,
    unit: hudTargets[5].id, accepted: true, reason: 'ok' } });
authorizedHatcheryWindow.onUpdate();
assert.equal(authorizedHatcheryWindow.widgets.find(
    widget => widget.name === 'building-feedback').text, 'Zergling training started');
zergButton.onClick();
registered.get('rtsbridge.commandResult').execute({ player: 1, args: {
    player: 1, request: actions.at(-1).args.request,
    unit: hudTargets[5].id, accepted: false, reason: 'native_train_rejected' } });
authorizedHatcheryWindow.onUpdate();
assert.equal(authorizedHatcheryWindow.widgets.find(
    widget => widget.name === 'building-feedback').text,
    'Training rejected: native_train_rejected');
const zergOrder = { session: sid, request: 981, unit_ids: [], verb: 'train',
    unit_type: 'zerg_zergling', target_entity_id: hudTargets[5].id };
assert.equal(command.query({ player: 1, args: zergOrder }).error, undefined,
    'authorized scenario server can order native Hatchery production');
assert.match(command.query({ player: 2, args: zergOrder }).errorMessage, /commander/,
    'Terran client cannot order enemy Hatchery production');
socket.handlers.data(JSON.stringify({ v: 1, kind: 'world.outcome', session: sid,
    payload: { scenario_id: 'frontier-outpost', state: 'victory', objective_id: 'openrct2:ride:17#1' } }) + '\n');
assert.equal(actions.filter(a => a.name === 'rtsbridge.worldOutcome').length, 1,
    'authoritative outcome uses a replicated OpenRCT2 action');
assert.match(command.query({ player: 1, args: squadArgs }).errorMessage, /ended/);
console.log('world plugin discovery and lifecycle validation passed');
