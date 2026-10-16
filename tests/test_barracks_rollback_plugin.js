const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const cells = new Map(), sent = [], replies = [], subscriptions = {}, actions = new Map();
const logs = [];
let storage = {}, socket;
function tile(x, y) {
    const key = `${x}:${y}`;
    if (!cells.has(key)) cells.set(key, [{ type: 'surface', baseHeight: 14, baseZ: 112,
        slope: 0, waterHeight: 0 }]);
    const elements = cells.get(key);
    return { numElements: elements.length, elements,
        getElement(index) { return elements[index]; } };
}
function deliver(kind, payload, revision = 1) {
    socket.handlers.data(JSON.stringify({ v: 1, kind, session: sent[0].session,
        revision, payload }) + '\n');
}
function drain() {
    while (replies.length) {
        const reply = replies.shift();
        deliver('world.ack', { op_id: reply.op_id, accepted: true }, reply.revision);
    }
}
function place() {
    for (let y = 2; y < 5; y++) for (let x = 2; x < 6; x++) {
        tile(x, y).elements.push({ type: 'large_scenery', object: 7,
            baseHeight: 14, baseZ: 112, direction: 0, sequence: (y - 2) * 4 + x - 2 });
    }
    subscriptions['action.execute']({ action: 'largesceneryplace',
        args: { x: 64, y: 64 }, result: {} });
}
const game = {
    map: { size: { x: 16, y: 16 }, rides: [], getTile: tile },
    objectManager: { getAllObjects(kind) { return kind === 'large_scenery' ? [{ index: 7,
        identifier: 'starcoaster.scenery_large.terran_barracks',
        tiles: Array.from({ length: 12 }, (_, index) => ({ offset: {
            x: index % 4 * 32, y: Math.floor(index / 4) * 32, z: 0 } })) }] : []; } },
    network: { mode: 'server', currentPlayer: { id: 1 }, players: [{ id: 1 }], createSocket() {
        socket = { handlers: {}, on(kind, callback) { this.handlers[kind] = callback; },
            connect(_port, _host, callback) { callback(); }, destroy() {},
            write(line) { const message = JSON.parse(line); sent.push(message); replies.push(message); } };
        return socket;
    } },
    rtsBridge: { version: 4, assetVersion: 3, applySnapshot() {},
        invalidateAnimation() {}, actorScreenPosition() {} },
    context: { getParkStorage() { return { get(key, fallback) { return storage[key] || fallback; },
        set(key, value) { storage[key] = structuredClone(value); } }; },
        registerAction(name, query, execute) { actions.set(name, { query, execute }); },
        subscribe(name, callback) { subscriptions[name] = callback; },
        executeAction(name, _args, callback) {
            if (name !== 'largesceneryremove') { callback({}); return; }
            assert.equal(name, 'largesceneryremove');
            for (let y = 2; y < 5; y++) for (let x = 2; x < 6; x++)
                cells.set(`${x}:${y}`, [tile(x, y).getElement(0)]);
            subscriptions['action.execute']({ action: name, args: { x: 64, y: 64 }, result: {} });
            callback({});
        } },
    console: { log(message) { logs.push(message); } },
    registerPlugin(plugin) { plugin.main(); },
};
vm.runInNewContext(fs.readFileSync('openrct2-plugin/rts-bridge.js', 'utf8'), game);
drain();
const marine = { id: 'openbw:100', kind: 'terran_marine', owner: 3, hp: 40,
    max_hp: 40, x: 400, y: 400, facing: 0, motion: 'idle', attack_frames: 0 };
actions.get('rtsbridge.applySnapshot').execute({ player: 1,
    args: { session: 'a'.repeat(32), seq: 1, units: [marine] } });
place();
for (let i = 0; i < 7; i++) subscriptions['interval.tick']();
drain();
const firstPatch = sent.find(message => message.kind === 'world.patch');
assert.ok(firstPatch);
assert.equal(firstPatch.payload.additions[0].owner, 3);
const firstID = firstPatch.payload.additions[0].id;
deliver('world.patch.status', { patch_id: firstPatch.payload.patch_id,
    state: 'unsynchronized', reason: 'controller:occupied_construction_geometry' }, 2);
drain();
assert.equal(tile(3, 3).numElements, 1, 'rejected park object is removed');
assert.ok(logs.some(line => line.includes('WORLD_BARRACKS_ROLLBACK_COMPLETE')));
const latestSnapshot = sent.filter(message => message.kind === 'world.snapshot.chunk')
    .slice(-2).flatMap(message => message.payload.entities || []);
assert.ok(!latestSnapshot.some(entity => entity.type === 'terran_barracks'));
place();
for (let i = 0; i < 7; i++) subscriptions['interval.tick']();
drain();
const secondPatch = sent.filter(message => message.kind === 'world.patch').at(-1);
assert.ok(secondPatch.payload.additions[0].id !== firstID,
    'reconstruction at the same site gets a new generation');
const secondID = secondPatch.payload.additions[0].id;
deliver('entity.target', { id: secondID, proxy_id: 'openbw:25', health: 23 });
assert.equal(storage.barracksHealth[secondID], 23,
    'native health is saved in park storage for a later real save');
console.log('Rejected Barracks rollback, resnapshot, native owner, and reconstruction generation passed');
