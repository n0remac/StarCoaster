const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const session = '0'.repeat(32), calls = [], actions = new Map(), handlers = {}, animations = [];
let stateCallback;
const cells = new Map();
function tile(x, y) {
    const key = `${x},${y}`;
    if (!cells.has(key)) cells.set(key, [{ type: 'surface', baseZ: 112,
        baseHeight: 14, hasConstructionRights: true }]);
    const elements = cells.get(key);
    return { numElements: elements.length, getElement(index) { return elements[index]; } };
}
const depot = { index: 17, identifier: 'starcoaster.scenery_large.terran_supply_depot',
    tiles: Array.from({ length: 6 }, (_, i) => ({ offset: {
        x: i % 3 * 32, y: Math.floor(i / 3) * 32, z: 0 } })) };
const context = { getParkStorage() { return { get(key, fallback) {
    return key === 'economyMode' ? 'finite' : fallback;
}, set() {} }; }, subscribe() {}, registerAction(name, query, execute) {
    actions.set(name, { query, execute });
}, executeAction(name, args, callback) {
    calls.push(name);
    if (name === 'rtsbridge.constructionState') {
        assert.equal(actions.get(name).query({ player: 1, args }).error, undefined);
        actions.get(name).execute({ player: 1, args });
        stateCallback = callback;
    } else if (name === 'rtsbridge.applySnapshot') {
        assert.equal(actions.get(name).query({ player: 1, args }).error, undefined);
        actions.get(name).execute({ player: 1, args });
        callback({});
    } else if (name === 'largesceneryplace') {
        assert.equal(animations.at(-1).tiles[0].frame, 1,
            'the base plate is registered before the park placement action');
        for (let dy = 0; dy < 2; dy++) for (let dx = 0; dx < 3; dx++)
            cells.get(`${args.x / 32 + dx},${args.y / 32 + dy}`).push({
                type: 'large_scenery', object: depot.index, baseHeight: 14,
                sequence: dy * 3 + dx, direction: 0 });
        callback({});
    } else callback({});
} };
const socket = { on(name, handler) { handlers[name] = handler; }, connect() {}, write() {}, destroy() {} };
const sandbox = {
    Math: Object.assign(Object.create(Math), { random() { return 0; } }),
    map: { size: { x: 8, y: 8 }, rides: [], getTile: tile },
    objectManager: { getAllObjects(kind) { return kind === 'large_scenery' ? [depot] : []; } },
    network: { mode: 'server', currentPlayer: { id: 1 }, players: [{ id: 1 }],
        createSocket() { return socket; } },
    rtsBridge: { version: 6, assetVersion: 7, clearSnapshot() {}, applySnapshot() {},
        invalidateAnimation() {}, setBuildingAnimations(value) { animations.push(value); },
        actorScreenPosition() {} },
    ui: { tileSelection: {}, registerViewportInteraction() {}, registerShortcut() {},
        registerMenuItem() {} },
    context, console: { log() {} }, registerPlugin(plugin) { plugin.main(); },
};
vm.runInNewContext(fs.readFileSync('openrct2-plugin/rts-bridge.js', 'utf8'), sandbox);
const message = { v: 1, session, kind: 'construction.state', payload: {
    intent_id: 'build:1:1', building_type: 'terran_supply_depot',
    tile_x: 2, tile_y: 3, native_id: '40', state: 'bound' } };
handlers.data(JSON.stringify(message) + '\n');
assert.deepEqual(calls, ['rtsbridge.constructionState']);
assert.equal(tile(2, 3).numElements, 1, 'projection waits for state action completion');
stateCallback({});
assert.deepEqual(calls, ['rtsbridge.constructionState'],
    'projection also waits for the first renderer snapshot');
handlers.data(JSON.stringify({ v: 1, session, revision: 1, kind: 'combat.snapshot',
    payload: { seq: 1, bw_tick: 1, units: [] } }) + '\n');
assert.deepEqual(calls, ['rtsbridge.constructionState', 'rtsbridge.applySnapshot',
    'largesceneryplace']);
assert.equal(tile(2, 3).numElements, 2);
