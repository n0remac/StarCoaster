const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const tiles = new Map();
function tile(x, y) {
    const key = `${x},${y}`;
    if (!tiles.has(key)) tiles.set(key, [{ type: 'surface', baseHeight: 14, baseZ: 112,
        slope: 0, waterHeight: 0 }]);
    const elements = tiles.get(key);
    return { numElements: elements.length, getElement(index) { return elements[index]; }, elements };
}
const windows = new Map(), actions = new Map(), menu = new Map();
let tool = null, passive = null, placements = 0, closedWindows = 0, frontedWindows = 0;
const orders = [], buildingAnimations = [];
const ui = {
    tileSelection: { tiles: [], range: null },
    get tool() { return tool; },
    openWindow(desc) {
        const window = { desc, findWidget(name) { return desc.widgets.find(widget => widget.name === name); },
            close() { closedWindows++; windows.delete(desc.classification);
                if (desc.onClose) desc.onClose(); },
            bringToFront() { frontedWindows++; } };
        windows.set(desc.classification, window);
        return window;
    },
    closeWindows(name) { windows.delete(name); },
    registerMenuItem(name, callback) { menu.set(name, callback); },
    registerShortcut() {},
    registerViewportInteraction(handler) { passive = handler; },
    activateTool(next) {
        if (tool) tool.cancel();
        tool = next;
        next.cancel = function () { tool = null; if (next.onFinish) next.onFinish(); };
    },
    showError(_title, message) { throw Error(message); },
};
const barracks = { index: 7, identifier: 'starcoaster.scenery_large.terran_barracks',
    tiles: Array.from({ length: 12 }, (_, i) => ({ offset: { x: i % 4 * 32,
        y: Math.floor(i / 4) * 32, z: 0 } })) };
const academy = { index: 8, identifier: 'starcoaster.scenery_large.terran_academy',
    tiles: Array.from({ length: 6 }, (_, i) => ({ offset: { x: i % 3 * 32,
        y: Math.floor(i / 3) * 32, z: 0 } })) };
const context = {
    registerAction(name, query, execute) { actions.set(name, { query, execute }); },
    subscribe() {},
    queryAction(name, args, callback) {
        assert.equal(name, 'largesceneryplace');
        let blocked = '';
        for (let y = args.y / 32; y < args.y / 32 + 3; y++)
            for (let x = args.x / 32; x < args.x / 32 + 4; x++)
                if (tile(x, y).numElements > 1) blocked = 'Blocked by park object';
                else if (tile(x, y).getElement(0).unowned) blocked = 'Land not owned';
        callback(blocked ? { error: 1, errorMessage: blocked } : {});
    },
    executeAction(name, args, callback) {
        if (name === 'rtsbridge.marineCommand') {
            orders.push(args); callback({}); return;
        }
        assert.equal(name, 'largesceneryplace');
        placements++;
        for (let y = args.y / 32; y < args.y / 32 + 3; y++)
            for (let x = args.x / 32; x < args.x / 32 + 4; x++)
                tile(x, y).elements.push({ type: 'large_scenery', object: 7, baseHeight: 14,
                    baseZ: 112, sequence: (y - args.y / 32) * 4 + x - args.x / 32 });
        callback({});
    },
};
const sandbox = {
    map: { size: { x: 16, y: 16 }, rides: [], getTile: tile },
    objectManager: { getAllObjects(kind) { return kind === 'large_scenery' ? [barracks, academy] : []; } },
    network: { mode: 'client', currentPlayer: { id: 1 }, players: [{ id: 1 }] },
    rtsBridge: { version: 5, assetVersion: 3, applySnapshot() {},
        invalidateAnimation() {}, setBuildingAnimations(state) { buildingAnimations.push(state); },
        actorScreenPosition() { return null; }, cursorWorld() { return null; } },
    ui, context, console: { log() {} }, registerPlugin(plugin) { plugin.main(); },
};
vm.runInNewContext(fs.readFileSync('openrct2-plugin/rts-bridge.js', 'utf8'), sandbox);
assert.equal(menu.has('StarCraft Construction'), true);
menu.get('StarCraft Construction')();
const construction = windows.get('starcoaster-construction');
assert.ok(construction);
menu.get('StarCraft Construction')();
assert.equal(frontedWindows, 1);
construction.desc.widgets.find(widget => widget.text && widget.text.startsWith('Barracks')).onClick();
assert.equal(tool.id, 'starcoaster.place-barracks');
const event = { mapCoords: { x: 64, y: 64 }, screenCoords: { x: 300, y: 300 } };
tool.onMove(event);
assert.equal(ui.tileSelection.tiles.length, 12);
assert.match(construction.findWidget('barracks-status').text, /Waiting for native units/);
tool.onDown(event);
assert.equal(placements, 0);
actions.get('rtsbridge.applySnapshot').execute({ player: 1,
    args: { session: 'a'.repeat(32), seq: 1, units: [] } });
tool.onMove(event);
assert.match(construction.findWidget('barracks-status').text, /Valid site/);
tool.onDown(event);
assert.equal(placements, 1);
assert.equal(tool, null);
assert.equal(tile(5, 4).numElements, 2);

// Barracks inspection consumes its own passive hit without selecting a Marine.
passive.onDown(event);
assert.equal(passive.onUp(event), true);
const info = windows.get('starcoaster-barracks-info');
assert.ok(info);
const targetID = 'openrct2:large_scenery:7:64:64:112:0#1';
const catalog = { session: 'a'.repeat(32), version: 1, index: 0, chunks: 1,
    targets: [{ id: targetID, rects: [{ x: 64, y: 64, width: 128, height: 96 }], health: 76 }] };
const action = actions.get('rtsbridge.targetCatalog');
assert.equal(action.query({ player: 1, args: catalog }).error, undefined);
action.execute({ player: 1, args: catalog });
info.desc.onUpdate();
assert.equal(info.findWidget('building-health').text, 'Health: 76');
assert.equal(info.findWidget('building-identity').text, 'Identity: awaiting native state');
const damaged = { ...catalog, version: 2, targets: [{ ...catalog.targets[0], health: 43 }] };
assert.equal(action.query({ player: 1, args: damaged }).error, undefined);
action.execute({ player: 1, args: damaged });
info.desc.onUpdate();
assert.equal(info.findWidget('building-health').text, 'Health: 43');
const nativeState = { session: 'a'.repeat(32), id: targetID, native_id: 'openbw:8',
    owner: 1, health: 1000, queue: 1, remaining_frames: 240, minerals: 450, gas: 250,
    supply_used: 12, supply_total: 16,
    availability: { terran_marine: { ready: true, reason: 'ready', requirement: '' },
        terran_firebat: { ready: false, reason: 'requires_building', requirement: 'Terran_Academy' } } };
const buildingAction = actions.get('rtsbridge.buildingState');
assert.equal(buildingAction.query({ player: 1, args: nativeState }).error, undefined);
buildingAction.execute({ player: 1, args: nativeState });
assert.equal(buildingAnimations.at(-1).session, nativeState.session);
assert.equal(buildingAnimations.at(-1).object, barracks.index);
assert.equal(buildingAnimations.at(-1).frames, 7);
assert.equal(buildingAnimations.at(-1).ticks_per_frame, 3);
assert.equal(buildingAnimations.at(-1).bank_stride, 48);
assert.equal(buildingAnimations.at(-1).tiles.length, 12);
assert.equal(buildingAnimations.at(-1).tiles[0].x, 64);
assert.equal(buildingAnimations.at(-1).tiles[0].y, 64);
buildingAction.execute({ player: 1, args: { ...nativeState, queue: 0, remaining_frames: 0 } });
assert.equal(buildingAnimations.at(-1).tiles.length, 0, 'completed training restores the idle frame');
buildingAction.execute({ player: 1, args: nativeState });
action.execute({ player: 1, args: { ...catalog, version: 3, targets: [] } });
assert.equal(buildingAnimations.at(-1).tiles.length, 0, 'demolition removes training animation');
action.execute({ player: 1, args: { ...catalog, version: 4 } });
info.desc.onUpdate();
assert.equal(info.findWidget('building-health').text, 'Health: 1000/1000');
assert.equal(info.findWidget('building-identity').text, 'Native: openbw:8  Generation: 1');
assert.match(info.findWidget('building-queue').text, /Queue: 1/);
assert.equal(info.findWidget('building-train').isDisabled, false);
assert.equal(info.findWidget('building-train-terran_firebat').isDisabled, true);
assert.match(info.findWidget('building-train-terran_firebat').text, /Requires Academy/);
info.findWidget('building-train').onClick();
assert.equal(orders.length, 1);
assert.equal(orders[0].verb, 'train');
assert.equal(orders[0].unit_type, 'terran_marine');
assert.equal(orders[0].target_entity_id, targetID);
assert.equal(orders[0].unit_ids.length, 0);
const resultAction = actions.get('rtsbridge.commandResult');
resultAction.execute({ player: 1, args: { player: 1, request: orders[0].request,
    unit: targetID, accepted: true, reason: 'ok' } });
info.desc.onUpdate();
assert.equal(info.findWidget('building-feedback').text, 'Marine training started');
buildingAction.execute({ player: 1, args: { ...nativeState, availability: {
    ...nativeState.availability,
    terran_firebat: { ready: true, reason: 'ready', requirement: '' } } } });
info.desc.onUpdate();
info.findWidget('building-train-terran_firebat').onClick();
assert.equal(orders[1].unit_type, 'terran_firebat');
resultAction.execute({ player: 1, args: { player: 1, request: orders[1].request,
    unit: targetID, accepted: true, reason: 'ok' } });
info.desc.onUpdate();
assert.equal(info.findWidget('building-feedback').text, 'Firebat training started');
const unsupportedTrain = actions.get('rtsbridge.marineCommand').query({ player: 1,
    args: { session: 'a'.repeat(32), request: 900, unit_ids: [], verb: 'train',
        unit_type: 'terran_medic', target_entity_id: targetID } });
assert.equal(unsupportedTrain.error, 1);
const resourcesAction = actions.get('rtsbridge.playerResources');
const resources = { session: 'a'.repeat(32), owner: 1, minerals: 999, gas: 250,
    supply_used: 12, supply_total: 16 };
assert.equal(resourcesAction.query({ player: 1, args: resources }).error, undefined);
resourcesAction.execute({ player: 1, args: resources });
info.desc.onUpdate();
assert.match(info.findWidget('building-resources').text, /Minerals: 999/);
passive.onDown(event);
assert.equal(passive.onUp(event), true);
assert.equal(closedWindows, 1, 'opening an existing Barracks closes its earlier info window');
assert.notEqual(windows.get('starcoaster-barracks-info'), info);

// Existing paths and occupied units both reject placement before native action.
tile(9, 2).elements.push({ type: 'footpath', baseHeight: 14 });
construction.desc.widgets.find(widget => widget.text && widget.text.startsWith('Barracks')).onClick();
const blocked = { mapCoords: { x: 256, y: 64 }, screenCoords: { x: 400, y: 300 } };
tool.onMove(blocked);
assert.match(construction.findWidget('barracks-status').text, /obstructed/);
tool.onDown(blocked);
assert.equal(placements, 1);
tile(9, 2).elements.pop();
tile(9, 2).elements[0].unowned = true;
tool.onMove(blocked);
assert.match(construction.findWidget('barracks-status').text, /Land not owned/);
tool.onDown(blocked);
assert.equal(placements, 1);
tile(9, 2).elements[0].unowned = false;
tile(9, 2).elements[0].slope = 1;
tool.onMove(blocked);
assert.match(construction.findWidget('barracks-status').text, /dry, flat ground/);
tool.onDown(blocked);
assert.equal(placements, 1);
tile(9, 2).elements[0].slope = 0;
const unit = { id: 'openbw:100', kind: 'terran_marine', owner: 1, hp: 40, max_hp: 40,
    x: 9 * 32, y: 2 * 32, facing: 0, motion: 'idle', attack_frames: 0 };
actions.get('rtsbridge.applySnapshot').execute({ player: 1,
    args: { session: 'a'.repeat(32), seq: 2, units: [unit] } });
tool.onMove(blocked);
assert.match(construction.findWidget('barracks-status').text, /unit occupies/);
tool.onDown(blocked);
assert.equal(placements, 1);
actions.get('rtsbridge.applySnapshot').execute({ player: 1,
    args: { session: 'a'.repeat(32), seq: 3, units: [{ ...unit, id: 'openbw:3001', x: 8 * 32 - 8 }] } });
tool.onMove(blocked);
assert.match(construction.findWidget('barracks-status').text, /unit occupies/,
    'unbound native actors overlapping the edge still occupy construction sites');
assert.equal(passive.onHover({ ...event, alt: true }), false);

// A completed non-production building has native identity and health, without
// Barracks queue controls.
assert.ok(construction.desc.widgets.some(widget => widget.text === 'Academy  |  3 x 2 tiles'));
for (let y = 10; y < 12; y++) for (let x = 10; x < 13; x++)
    tile(x, y).elements.push({ type: 'large_scenery', object: academy.index,
        baseHeight: 14, baseZ: 112, sequence: (y - 10) * 3 + x - 10 });
const academyID = 'openrct2:large_scenery:8:320:320:112:0#1';
action.execute({ player: 1, args: { ...catalog, version: 5,
    targets: [catalog.targets[0], { id: academyID,
        rects: [{ x: 320, y: 320, width: 96, height: 64 }], health: 600 }] } });
const academyEvent = { mapCoords: { x: 320, y: 320 }, screenCoords: { x: 450, y: 400 } };
passive.onDown(academyEvent);
assert.equal(passive.onUp(academyEvent), true);
const academyInfo = windows.get('starcoaster-building-info');
assert.ok(academyInfo);
buildingAction.execute({ player: 1, args: { ...nativeState, id: academyID,
    native_id: 'openbw:9', health: 600, max_health: 600, queue: 0,
    remaining_frames: 0, availability: {} } });
academyInfo.desc.onUpdate();
assert.equal(academyInfo.findWidget('building-health').text, 'Health: 600/600');
assert.equal(academyInfo.findWidget('building-identity').text, 'Native: openbw:9  Generation: 1');
assert.equal(academyInfo.findWidget('building-status').text, 'Construction: complete');
assert.equal(academyInfo.findWidget('building-queue'), undefined);
assert.equal(academyInfo.findWidget('building-train'), undefined);

// Park storage keeps the structure ID stable when the plugin restarts on a saved park.
let savedStorage = {};
function discoverAfterLoad() {
    const placed = new Map();
    for (let y = 2; y < 5; y++) for (let x = 2; x < 6; x++) {
        placed.set(`${x},${y}`, [{ type: 'surface', baseHeight: 14, baseZ: 112 },
            { type: 'large_scenery', object: 7, baseHeight: 14, direction: 0,
                sequence: (y - 2) * 4 + x - 2 }]);
    }
    const sent = [], responses = [];
    let socket;
    const game = {
        map: { size: { x: 16, y: 16 }, rides: [], getTile(x, y) {
            const elements = placed.get(`${x},${y}`) || [{ type: 'surface', baseHeight: 14, baseZ: 112 }];
            return { numElements: elements.length, getElement(index) { return elements[index]; } };
        } },
        objectManager: { getAllObjects(kind) { return kind === 'large_scenery' ? [barracks] : []; } },
        network: { mode: 'server', currentPlayer: { id: 1 }, players: [{ id: 1 }], createSocket() {
            socket = { handlers: {}, on(kind, callback) { this.handlers[kind] = callback; },
                connect(_port, _host, callback) { callback(); }, destroy() {},
                write(line) {
                    const message = JSON.parse(line); sent.push(message);
                    responses.push(JSON.stringify({ v: 1, kind: 'world.ack', session: message.session,
                        payload: { op_id: message.op_id, accepted: true } }) + '\n');
                } };
            return socket;
        } },
        rtsBridge: { version: 5, assetVersion: 3, applySnapshot() {},
            invalidateAnimation() {}, setBuildingAnimations() {}, actorScreenPosition() {} },
        context: { getParkStorage() { return { get(key, fallback) { return savedStorage[key] || fallback; },
            set(key, value) { savedStorage[key] = structuredClone(value); } }; },
            registerAction() {}, subscribe() {}, executeAction() {} },
        console: { log() {} }, registerPlugin(plugin) { plugin.main(); },
    };
    vm.runInNewContext(fs.readFileSync('openrct2-plugin/rts-bridge.js', 'utf8'), game);
    while (responses.length) socket.handlers.data(responses.shift());
    return sent.filter(message => message.kind === 'world.snapshot.chunk')
        .flatMap(message => message.payload.entities || [])
        .find(entity => entity.type === 'terran_barracks');
}
const firstLoad = discoverAfterLoad();
assert.ok(firstLoad);
assert.equal(firstLoad.kind, 'structure');
assert.equal(firstLoad.owner, 1);
assert.equal(firstLoad.geometry.cells.length, 12);
assert.equal(discoverAfterLoad().id, firstLoad.id);
console.log('Barracks menu, footprint, placement, inspection, and obstruction validation passed');
