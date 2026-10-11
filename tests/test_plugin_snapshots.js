const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const applied = [];
const events = {};
let query;
let execute;
let socket;
const sandbox = {
    console: { log() {} },
    map: { size: { x: 128, y: 128 } },
    network: {
        mode: 'server', currentPlayer: { id: 1 }, numPlayers: 3,
        createSocket() {
            socket = { handlers: {}, on(name, callback) { this.handlers[name] = callback; },
                connect(_port, _host, callback) { callback(); }, destroy() {} };
            return socket;
        }
    },
    rtsBridge: { version: 4, assetVersion: 3,
        applySnapshot(value) { applied.push(value); }, invalidateAnimation() {} },
    context: {
        registerAction(_name, q, e) { query = q; execute = e; },
        executeAction(_name, args, callback) {
            const result = query({ player: 1, args });
            if (!result.error) execute({ player: 1, args });
            callback(result);
        },
        subscribe(name, callback) { events[name] = callback; }
    },
    registerPlugin(plugin) { plugin.main(); }
};
vm.runInNewContext(fs.readFileSync('openrct2-plugin/rts-bridge.js', 'utf8'), sandbox);
const sessionA = 'a'.repeat(32);
const sessionB = 'b'.repeat(32);
const unit = id => ({ id: `openbw:${id}`, kind: 'alien_scout', x: 320 + id * 8, y: 480,
    facing: id % 256, motion: id % 2 ? 'walk' : 'idle', alive: true });
const packet = (session, seq, units) => ({ v: 1, kind: 'units.snapshot', session,
    map_id: 'demo-flat', seq, bw_tick: seq * 3, units });
const send = value => socket.handlers.data(JSON.stringify(value) + '\n');

send(packet(sessionA, 1, [unit(1)]));
assert.equal(applied.length, 1, 'single-unit v1 packet remains valid');
send(packet(sessionA, 2, Array.from({ length: 8 }, (_, i) => unit(i + 1))));
assert.equal(applied.length, 2);
assert.equal(applied[1].units.length, 8);
send(packet(sessionA, 2, [unit(1)]));
assert.equal(applied.length, 2, 'duplicate sequence rejected');
send(packet(sessionA, 1, [unit(1)]));
assert.equal(applied.length, 2, 'old sequence rejected');
for (const bad of [
    [unit(1), unit(1)],
    [unit(1), { ...unit(2), x: 4096 }],
    [unit(1), { ...unit(2), facing: 256 }],
    [unit(1), { ...unit(2), motion: 'attack' }],
    Array.from({ length: 33 }, (_, i) => unit(i + 1))
]) {
    send(packet(sessionA, 3, bad));
    assert.equal(applied.length, 2, 'invalid array rejected atomically');
}
socket.handlers.data('{malformed}\n');
assert.equal(applied.length, 2);
send(packet(sessionA, 3, []));
assert.equal(applied.length, 3, 'full empty snapshot despawns squad');
send(packet(sessionB, 1, [unit(3)]));
assert.equal(applied.length, 4, 'new session resets sequence');
send(packet(sessionA, 99, [unit(1)]));
assert.equal(applied.length, 4, 'retired session cannot resurrect actor');
const maximum = Array.from({ length: 32 }, (_, i) => unit(i + 1));
send(packet(sessionB, 2, maximum));
assert.equal(applied.length, 5, '32-unit capacity is supported');
assert.equal(applied[4].units.length, 32);
const worstCase = packet(sessionB, 3, maximum.map((entry, index) => ({ ...entry,
    id: `openbw:${String(index).padStart(25, '9')}`, x: 4095, y: 4095, facing: 255 })));
assert.ok(Buffer.byteLength(JSON.stringify(worstCase), 'utf8') < 16384);
assert.equal(query({ player: 2, args: applied[3] }).error, 1, 'only server player may act');
assert.equal(query({ player: 1, args: { session: sessionB, seq: 2, units: [
    { id: 'openbw:1', x: 1, y: 1, facing: 0, motion: 'walk' },
    { id: 'openbw:1', x: 2, y: 1, facing: 0, motion: 'walk' }
] } }).error, 1, 'synchronized action rejects duplicate actors');
socket.handlers.data('x'.repeat(16385) + '\n');
assert.equal(applied.length, 5, 'oversized wire input never becomes a partial action');
console.log('plugin snapshot validation passed');
