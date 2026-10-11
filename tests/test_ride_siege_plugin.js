const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const source = fs.readFileSync('openrct2-plugin/rts-bridge.js', 'utf8')
    .replace('const SIEGE_ENABLED = false;', 'const SIEGE_ENABLED = true;');

function fixture(rejectDemolition = false) {
    const messages = [];
    const actions = [];
    const applied = [];
    const tiles = new Map();
    for (let x = 18; x <= 20; x++) for (let y = 14; y <= 16; y++) {
        tiles.set(`${x},${y}`, [{ type: 'track', ride: 100, baseHeight: 14, trackType: 266 }]);
    }
    let ride = { id: 100, name: 'Frontier Carousel', type: 33,
        object: { identifier: 'rct2.ride.mgr1' }, status: 'closed', isEmpty: true };
    let socket;
    let query, execute;
    const map = { size: { x: 128, y: 128 }, get rides() { return ride ? [ride] : []; },
        getRide(id) { return ride && ride.id === id ? ride : null; },
        getTile(x, y) { const elements = tiles.get(`${x},${y}`) || [];
            return { numElements: elements.length, getElement(index) { return elements[index]; } }; } };
    const sandbox = {
        console: { log(value) { messages.push(value); } }, map,
        network: { mode: 'server', currentPlayer: { id: 1 }, numPlayers: 3,
            createSocket() { socket = { handlers: {}, on(name, cb) { this.handlers[name] = cb; },
                connect(_port, _host, cb) { cb(); }, destroy() {} }; return socket; } },
        rtsBridge: { version: 1, assetVersion: 1,
            applySnapshot(value) { applied.push(value); }, invalidateAnimation() {} },
        context: { registerAction(_name, q, e) { query = q; execute = e; }, subscribe() {},
            executeAction(name, args, callback) {
                actions.push(name);
                if (name === 'ridedemolish') {
                    if (!rejectDemolition) {
                        ride = null;
                        for (const key of tiles.keys()) tiles.set(key, []);
                    }
                    callback(rejectDemolition ? { error: 1, errorMessage: 'rejected' } : {});
                } else {
                    const result = query({ player: 1, args });
                    if (!result.error) execute({ player: 1, args });
                    callback(result);
                }
            } },
        registerPlugin(plugin) { plugin.main(); }
    };
    vm.runInNewContext(source, sandbox);
    const send = packet => socket.handlers.data(JSON.stringify(packet) + '\n');
    return { send, messages, actions, applied, getRide: () => ride,
        changeRide(value) { ride = value; } };
}

const session = 'a'.repeat(32);
const unit = id => ({ id: `openbw:${id}`, kind: 'alien_scout', x: 544, y: 488,
    facing: 0, motion: 'walk', alive: true });
const packet = (seq, hp, state, sid = session) => ({ v: 2, kind: 'scenario.snapshot',
    session: sid, map_id: 'ride-siege', seq, bw_tick: seq * 3, units: [unit(0)],
    targets: [{ id: 'carousel-1', proxy_unit_id: 'openbw:8', hp, max_hp: 200, state }] });

{
    const f = fixture();
    assert.ok(f.messages.some(x => x.startsWith('RIDE_SIEGE_READY')));
    f.send(packet(1, 200, 'intact'));
    f.send(packet(2, 195, 'damaged'));
    assert.equal(f.actions.filter(x => x === 'ridedemolish').length, 0);
    assert.equal(f.applied[1].units[0].x, 416, 'OpenBW coordinates map to park approach');
    f.send({ ...packet(3, 0, 'destroyed'), targets: [{ ...packet(3, 0, 'destroyed').targets[0], id: 'wrong' }] });
    assert.ok(f.getRide(), 'unknown target cannot demolish');
    f.send(packet(3, 0, 'destroyed'));
    assert.equal(f.getRide(), null);
    assert.equal(f.actions.filter(x => x === 'ridedemolish').length, 1);
    f.send(packet(4, 0, 'destroyed'));
    f.send(packet(1, 200, 'intact', 'b'.repeat(32)));
    assert.equal(f.actions.filter(x => x === 'ridedemolish').length, 1);
    assert.ok(f.messages.some(x => x.startsWith('RIDE_SIEGE_DEMOLITION_SUCCEEDED')));
}
{
    const f = fixture(true);
    f.send(packet(1, 200, 'intact'));
    f.send(packet(2, 0, 'destroyed'));
    f.send(packet(3, 0, 'destroyed'));
    assert.ok(f.getRide(), 'failed action leaves ride intact');
    assert.equal(f.actions.filter(x => x === 'ridedemolish').length, 1);
    assert.ok(f.messages.some(x => x.startsWith('RIDE_SIEGE_DEMOLITION_FAILED')));
}
{
    const f = fixture();
    f.send(packet(1, 200, 'intact'));
    f.changeRide({ ...f.getRide(), name: 'Different ride' });
    f.send(packet(2, 0, 'destroyed'));
    assert.equal(f.actions.filter(x => x === 'ridedemolish').length, 0);
}
console.log('ride siege coordinator validation passed');
