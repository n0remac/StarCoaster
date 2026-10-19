const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const handlers = new Map();
const logs = [];
const structure = { id: 'western-hatchery', type: 'zerg_hatchery',
    x: 8, y: 31, z: 112, owner: 0 };
const object = { index: 7, identifier: 'starcoaster.scenery_large.zerg_hatchery' };
const sandbox = {
    map: { size: { x: 202, y: 202 }, getTile(x, y) {
        const elements = x === 8 && y === 31
            ? [{ type: 'surface', baseHeight: 14 },
                { type: 'large_scenery', object: 7, baseHeight: 14, sequence: 0 }]
            : [{ type: 'surface', baseHeight: 14 }];
        return { numElements: elements.length, getElement(index) { return elements[index]; } };
    } },
    objectManager: { getAllObjects(kind) { return kind === 'large_scenery' ? [object] : []; } },
    network: { mode: 'server', currentPlayer: { id: 1 }, players: [{ id: 1 }, { id: 2 }],
        createSocket() { return { on() {}, connect() {}, destroy() {} }; } },
    rtsBridge: { version: 5, assetVersion: 4, cursorWorld() {}, invalidateAnimation() {},
        setBuildingAnimations() {}, applySnapshot() {}, clearSnapshot() {}, actorScreenPosition() {} },
    context: { getParkStorage() { return { get(key, fallback) {
        return key === 'scenarioStructures' ? [structure] : fallback;
    }, set() {} }; }, subscribe(name, handler) {
        if (name === 'action.query') handlers.set(name, handler);
    }, registerAction() {}, executeAction() {} },
    console: { log(line) { logs.push(line); } },
    registerPlugin(plugin) { plugin.main(); },
};
vm.runInNewContext(fs.readFileSync('openrct2-plugin/rts-bridge.js', 'utf8'), sandbox);
const query = handlers.get('action.query');
assert.ok(query);
function check(action, args, player = 2) {
    const event = { action, args, player, result: {} };
    query(event);
    return event.result;
}
assert.equal(check('largesceneryremove', { x: 8 * 32, y: 31 * 32 }).error, 1);
assert.equal(check('landraise', { x1: 7 * 32, y1: 30 * 32,
    x2: 10 * 32, y2: 34 * 32 }).error, 1);
assert.equal(check('clearscenery', { x1: 8 * 32, y1: 31 * 32,
    x2: 9 * 32, y2: 32 * 32 }).error, 1);
assert.equal(check('largesceneryremove', { x: 30 * 32, y: 31 * 32 }).error, undefined);
assert.equal(check('largesceneryremove', { x: 8 * 32, y: 31 * 32 }, 1).error, undefined,
    'server combat removal remains available');
assert.equal(logs.filter(line => line.startsWith('WORLD_ENEMY_STRUCTURE_BLOCK')).length, 3);
