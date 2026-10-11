const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const source = fs.readFileSync('openrct2-plugin/rts-bridge.js', 'utf8')
    .replace('const FRONTIER_ENABLED = false;', 'const FRONTIER_ENABLED = true;');
const actions = new Map();
const subscriptions = new Map();
const sockets = [];
const applied = [];
const messages = [];
const shortcuts = new Map();
let selectionTool;
const ride = { id: 100, name: 'Frontier Carousel', type: 33,
    object: { identifier: 'rct2.ride.mgr1' }, status: 'closed', isEmpty: true };
const sandbox = {
    console: { log(value) { messages.push(value); } },
    map: { size: { x: 128, y: 128 }, rides: [ride], getRide() { return ride; },
        getTile(x, y) { const matching = x >= 18 && x <= 20 && y >= 14 && y <= 16;
            return { numElements: matching ? 1 : 0, getElement() {
                return { type: 'track', ride: 100, baseHeight: 14, trackType: 266 }; } }; } },
    network: { mode: 'server', currentPlayer: { id: 1 }, players: [{ id: 1 }, { id: 2 }], numPlayers: 3,
        createSocket() { const socket = { handlers: {}, sent: [], on(name, fn) { this.handlers[name] = fn; },
            connect(_port, _host, fn) { fn(); }, destroy() {}, write(value) { this.sent.push(value); return true; } };
            sockets.push(socket); return socket; } },
    rtsBridge: { version: 4, assetVersion: 3, applySnapshot(value) { applied.push(value); },
        invalidateAnimation() {}, hitTest(x) {
            return ({ 512: 'openbw:1', 520: 'openbw:3', 432: 'openbw:2' })[x] || null;
        } },
    ui: { registerShortcut(value) { shortcuts.set(value.id, value.callback); },
        activateTool(value) { selectionTool = value; }, showError(message) { throw new Error(message); } },
    context: { registerAction(name, query, execute) { actions.set(name, { query, execute }); },
        subscribe(name, callback) {
            if (!subscriptions.has(name)) subscriptions.set(name, []);
            subscriptions.get(name).push(callback);
        }, executeAction(name, args, callback) {
            const action = actions.get(name);
            if (!action) throw new Error(name);
            const result = action.query({ player: 1, args });
            if (!result.error) action.execute({ player: 1, args });
            callback(result);
        } },
    registerPlugin(plugin) { plugin.main(); }
};
vm.runInNewContext(source, sandbox);
const session = 'a'.repeat(32);
const unit = (id, kind, owner, x) => ({ id: `openbw:${id}`, kind, owner, x, y: 480,
    facing: 0, motion: 'idle', hp: kind === 'terran_marine' ? 40 : 35,
    max_hp: kind === 'terran_marine' ? 40 : 35, alive: true, attack_frames: 0, target_id: null });
const packet = (seq, units, events = []) => ({ v: 3, kind: 'scenario.snapshot', session,
    map_id: 'frontier-defense', seq, bw_tick: seq * 3, units, events,
    targets: [{ id: 'carousel-1', proxy_unit_id: 'openbw:12', hp: 200, max_hp: 200, state: 'intact' }] });
const units = [unit(1, 'terran_marine', 1, 640), unit(2, 'zerg_zergling', 0, 560),
    unit(3, 'terran_marine', 1, 648)];
const send = value => sockets[0].handlers.data(JSON.stringify(value) + '\n');
send(packet(1, units));
assert.equal(applied.length, 1);
assert.equal(applied[0].units[0].kind, 'terran_marine');
assert.equal(applied[0].units[0].x, 512);
send(packet(2, [units[0], units[0]]));
assert.equal(applied.length, 1, 'duplicate IDs are rejected');
send(packet(2, [{ ...units[0], hp: -1 }, units[1]]));
assert.equal(applied.length, 1, 'malformed health is rejected');
const damage = { id: `${session}:6:damage:2`, kind: 'damage', unit_id: 'openbw:2',
    value: 6, bw_tick: 6 };
send(packet(2, [units[0], { ...units[1], hp: 29, motion: 'attack', attack_frames: 1 }, units[2]], [damage]));
assert.equal(applied.length, 2);
assert.equal(messages.filter(value => value.includes('combat event=damage')).length, 1);
send(packet(3, [units[0], { ...units[1], hp: 29 }, units[2]], [damage]));
assert.equal(messages.filter(value => value.includes('combat event=damage')).length, 1,
    'an event replay does not retrigger effects');
const command = actions.get('rtsbridge.marineCommand');
const args = { session, request: 7, unit_ids: ['openbw:1'], verb: 'move', x: 790, y: 440 };
assert.equal(command.query({ player: 2, args }).error, undefined);
assert.equal(command.query({ player: 2, args: { ...args, unit_ids: ['openbw:2'] } }).error, 1,
    'enemy units cannot be commanded');
assert.equal(command.query({ player: 2, args: { ...args, verb: 'attack', target_id: 'openbw:1' } }).error, 1);
command.execute({ player: 2, args });
assert.match(sockets[1].sent[0], /^order a{32} 1 1 move 790 440\n$/);
sockets[1].handlers.data(`ack ${session} 1 accepted ok\n`);
assert.ok(messages.some(value => value.includes('accepted=true')) === false,
    'only the requesting player sees the command result');
selectionTool.onDown({ mapCoords: { x: 512, y: 384 }, shift: false });
selectionTool.onDown({ mapCoords: { x: 520, y: 384 }, shift: true });
selectionTool.onRightClick({ mapCoords: { x: 600, y: 390 } });
assert.match(sockets[1].sent.at(-2), /^order a{32} \d+ 1 move 728 486\n$/);
assert.match(sockets[1].sent.at(-1), /^order a{32} \d+ 3 move 728 486\n$/);
selectionTool.onRightClick({ mapCoords: { x: 432, y: 384 } });
assert.match(sockets[1].sent.at(-2), /^order a{32} \d+ 1 attack 2 0\n$/);
assert.match(sockets[1].sent.at(-1), /^order a{32} \d+ 3 attack 2 0\n$/);
shortcuts.get('starcoaster.hold-position')();
assert.match(sockets[1].sent.at(-1), /^order a{32} \d+ 3 hold 0 0\n$/);
selectionTool.onDown({ mapCoords: { x: 512, y: 384 }, shift: true });
selectionTool.onRightClick({ mapCoords: { x: 600, y: 390 } });
assert.match(sockets[1].sent.at(-1), /^order a{32} \d+ 3 move 728 486\n$/,
    'Shift-click removes a Marine from the selection');
sockets[0].handlers.close();
assert.equal(applied.at(-1).units.length, 0, 'publisher disconnect removes native actors');
for (let tick = 0; tick < 40; ++tick)
    subscriptions.get('interval.tick').forEach(function (callback) { callback(); });
assert.ok(sockets[2], 'publisher socket reconnects');
sockets[2].handlers.data(JSON.stringify(packet(5, units)) + '\n');
assert.equal(applied.at(-1).units.length, 3, 'live units return after reconnect');
console.log('mixed combat snapshot and Marine command validation passed');
