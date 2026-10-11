const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const names = ['carousel-1', 'shop-1', 'ride-2'];
const config = { scenario: 'park-assault', map_id: 'park-assault',
    bounds: { min_x: 8, min_y: 8, max_x: 55, max_y: 55 }, transform: { x: -128, y: -96 },
    targets: names.map((id, i) => ({ id, ride_id: [7, 9, 11][i], ride_type: [33, 28, 37][i],
        name: ['Frontier Carousel', 'Frontier Burger Bar', 'Frontier Ferris Wheel'][i],
        object_id: ['rct2.ride.mgr1', 'rct2.ride.burgb', 'rct2.ride.fwh1'][i],
        status: 'closed', max_hp: 1000,
        tiles: [{ x: 18 + i * 10, y: 19 + i * 10, z: 112, track_type: 266 - i }] })) };
const source = 'var STARCOASTER_SCENARIO_CONFIG = ' + JSON.stringify(config) + ';\n'
    + fs.readFileSync('openrct2-plugin/rts-bridge.js', 'utf8');

function fixture(failedTarget = null) {
    const messages = [], actions = [], applied = [], rides = new Map(), tracks = new Map();
    config.targets.forEach((target) => {
        rides.set(target.ride_id, { id: target.ride_id, name: target.name, type: target.ride_type,
            object: { identifier: target.object_id }, status: 'closed', isEmpty: true });
        tracks.set(`${target.tiles[0].x},${target.tiles[0].y}`, [{ type: 'track', ride: target.ride_id,
            baseHeight: 14, trackType: target.tiles[0].track_type }]);
    });
    const sockets = [];
    const actionMap = new Map();
    const map = { size: { x: 128, y: 128 }, get rides() { return [...rides.values()]; },
        getRide(id) { return rides.get(id) || null; }, getTile(x, y) {
            const elements = tracks.get(`${x},${y}`) || [];
            return { numElements: elements.length, getElement(index) { return elements[index]; } };
        } };
    const sandbox = { map, console: { log(line) { messages.push(line); } },
        network: { mode: 'server', currentPlayer: { id: 1 }, numPlayers: 3,
            createSocket() { const socket = { handlers: {}, sent: [],
                on(name, callback) { this.handlers[name] = callback; },
                connect(_port, _host, callback) { callback(); },
                write(line) { this.sent.push(line); return true; }, destroy() {} };
                sockets.push(socket); return socket; } },
        rtsBridge: { version: 4, assetVersion: 3, applySnapshot(value) { applied.push(value); },
            invalidateAnimation() {} },
        context: { registerAction(name, query, execute) { actionMap.set(name, { query, execute }); },
            subscribe() {}, executeAction(name, args, callback) {
                actions.push({ name, args });
                if (name === 'ridedemolish') {
                    if (config.targets.find(target => target.ride_id === args.ride).id === failedTarget)
                        callback({ error: 1, errorMessage: 'probe rejection' });
                    else {
                        rides.delete(args.ride);
                        for (const [key, elements] of tracks)
                            tracks.set(key, elements.filter(element => element.ride !== args.ride));
                        callback({});
                    }
                    return;
                }
                const action = actionMap.get(name);
                const result = action.query({ player: 1, args });
                if (!result.error) action.execute({ player: 1, args });
                callback(result);
            } }, registerPlugin(plugin) { plugin.main(); } };
    vm.runInNewContext(source, sandbox);
    return { messages, actions, applied, rides, sockets,
        send(packet) { sockets[0].handlers.data(JSON.stringify(packet) + '\n'); } };
}

const session = 'a'.repeat(32);
const unit = i => ({ id: `openbw:${i + 1}`, kind: 'zerg_zergling', owner: 0,
    x: 500 + i * 8, y: 600, facing: i, motion: 'walk', hp: 35, max_hp: 35,
    alive: true, attack_frames: 0, target_id: null });
const targets = (hp = [1000, 1000, 1000]) => names.map((id, i) => ({ id,
    proxy_unit_id: `openbw:${100 + i}`, hp: hp[i], max_hp: 1000,
    state: hp[i] === 0 ? 'destroyed' : hp[i] === 1000 ? 'intact' : 'damaged' }));
const packet = (seq, hp, revision = 1, sid = session) => ({ v: 3, kind: 'scenario.snapshot',
    session: sid, map_id: 'park-assault', seq, bw_tick: seq * 3,
    map_revision: revision, units: Array.from({ length: 20 }, (_, i) => unit(i)),
    targets: targets(hp), events: [] });
const capacityPacket = { ...packet(999999999, [1000, 1000, 1000]),
    units: Array.from({ length: 32 }, (_, i) => ({ ...unit(i), x: 4095, y: 4095,
        facing: 255, attack_frames: 999999999, target_id: 'openbw:999999999' })),
    events: Array.from({ length: 64 }, (_, i) => ({
        id: `${session}:999999999:attack_frame:${i}`, kind: 'attack_frame',
        unit_id: 'openbw:999999999', value: 999999999, bw_tick: 999999999 * 3 })) };
assert.ok(Buffer.byteLength(JSON.stringify(capacityPacket) + '\n') < 32768,
    '32 actors, three targets, and 64 events must fit the configured transport limit');

{
    const f = fixture();
    assert.ok(f.messages.some(line => line.startsWith('PARK_ASSAULT_READY')));
    f.send(packet(1, [1000, 1000, 1000]));
    assert.equal(f.applied.length, 1);
    assert.equal(f.applied[0].units.length, 20);
    assert.equal(f.applied[0].units[0].x, 372);
    f.send({ ...packet(2, [1000, 1000, 1000]), targets: targets().slice(0, 2) });
    f.send({ ...packet(2, [1000, 1000, 1000]), units: [unit(0), unit(0)] });
    f.send({ ...packet(2, [1000, 1000, 1000]), events: [{
        id: `${session}:6:damage:1`, kind: 'invalid', unit_id: 'openbw:1',
        value: 1, bw_tick: 6 }] });
    f.send(packet(2, [1000, 1000, 1000], 9));
    assert.equal(f.applied.length, 1, 'malformed, duplicate and future-revision packets are rejected');
    f.send(packet(2, [950, 1000, 1000]));
    f.send(packet(3, [980, 1000, 1000]));
    assert.equal(f.applied.length, 2, 'HP regression is rejected');
    f.send(packet(3, [0, 0, 0]));
    assert.equal(f.actions.filter(entry => entry.name === 'ridedemolish').length, 3);
    assert.equal(f.rides.size, 0);
    assert.deepEqual(Array.from(f.sockets[0].sent), names.map((id, i) => `nav ${session} ${i + 2} ${id}\n`));
    f.send(packet(4, [0, 0, 0], 4));
    f.send(packet(5, [1000, 1000, 1000], 1, 'b'.repeat(32)));
    assert.equal(f.actions.filter(entry => entry.name === 'ridedemolish').length, 3,
        'destroyed packets and a new session cannot trigger duplicate demolition');
}
{
    const f = fixture('shop-1');
    f.send(packet(1, [1000, 1000, 1000]));
    f.send(packet(2, [0, 0, 0]));
    f.send(packet(3, [0, 0, 0]));
    assert.ok(f.rides.has(9), 'rejected native demolition retains the original ride');
    assert.equal(f.actions.filter(entry => entry.name === 'ridedemolish' && entry.args.ride === 9).length, 1);
    assert.ok(f.messages.some(line => line.startsWith('PARK_ASSAULT_DEMOLITION_FAILED id=shop-1')));
}
console.log('park assault three-target coordinator validation passed');
