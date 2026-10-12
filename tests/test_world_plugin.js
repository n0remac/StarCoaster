const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const tiles = new Map();
function at(x, y) { const key = `${x},${y}`; if (!tiles.has(key)) tiles.set(key, [{ type: 'surface', baseHeight: 14, waterHeight: 0, surfaceObject: 1 }]); return tiles.get(key); }
let ride = { id: 17, name: 'Any Carousel', type: 33, classification: 'ride',
    object: { identifier: 'rct2.ride.mgr1' }, status: 'closed', isEmpty: true };
at(1, 1).push({ type: 'track', ride: 17, baseHeight: 14 });
at(1, 2).push({ type: 'track', ride: 17, baseHeight: 14 });
at(4, 1).push({ type: 'small_scenery', object: 2, baseHeight: 14, quadrant: 0, direction: 0 });
at(5, 1).push({ type: 'wall', object: 3, baseHeight: 14, direction: 1 });
at(5, 2).push({ type: 'footpath', object: 4, surfaceObject: 4, baseHeight: 14 });
at(2, 3).push({ type: 'large_scenery', object: 1, sequence: 0, baseHeight: 14, direction: 0 });
at(3, 3).push({ type: 'large_scenery', object: 1, sequence: 1, baseHeight: 14, direction: 0 });
const sent = [], actions = [], applied = [], logs = [], registered = new Map(), responses = [], subscriptions = new Map();
let socket;
const sandbox = {
    STARCOASTER_WORLD_BRIDGE: true,
    map: { size: { x: 8, y: 8 }, get rides() { return ride ? [ride] : []; },
        getRide(id) { return ride && id === ride.id ? ride : null; },
        getTile(x, y) { const elements = at(x, y); return { numElements: elements.length,
            getElement(index) { return elements[index]; } }; } },
    objectManager: { getAllObjects(kind) {
        if (kind === 'large_scenery') return [{ index: 1, identifier: 'rct2.scenery_large.test',
            tiles: [{ offset: { x: 0, y: 0, z: 0 } }, { offset: { x: 32, y: 0, z: 0 } }] }];
        if (kind === 'small_scenery') return [{ index: 2, identifier: 'rct2.scenery_small.tree' }];
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
    rtsBridge: { version: 4, assetVersion: 3, invalidateAnimation() {}, applySnapshot(snapshot) { applied.push(snapshot); } },
    context: { registerAction(name, query, execute) { registered.set(name, { query, execute }); },
        subscribe(name, callback) { subscriptions.set(name, callback); }, executeAction(name, args, callback) { actions.push({ name, args });
            if (name === 'ridedemolish') {
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
assert.equal(all.length, 5);
assert.deepEqual([...new Set(all.map(e => e.kind))].sort(), ['large_scenery', 'path', 'ride', 'small_scenery', 'wall']);
const large = all.find(e => e.kind === 'large_scenery');
assert.equal(large.geometry.cells.length, 2, 'multi-tile object retains one identity');
assert.equal(large.geometry.rects[0].width, 64, 'adjacent cells merge into one collision rectangle');
assert.equal(all.find(e => e.kind === 'wall').geometry.rects[0].width, 4,
    'wall collision uses a thin segment rather than a whole tile');
assert.equal(sent.filter(m => m.kind === 'world.snapshot.chunk').length, begin.payload.chunks);
const sid = begin.session;
socket.handlers.data(JSON.stringify({ v: 1, kind: 'combat.snapshot', session: sid,
    payload: { seq: 1, bw_tick: 3, units: [{ id: 'openbw:7', kind: 'zerg_zergling', owner: 0,
        x: 48, y: 48, facing: 0, motion: 'walk', hp: 35, max_hp: 35, attack_frames: 0 }] } }) + '\n');
assert.equal(applied.length, 1, 'combat actors use synchronized native action');
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
const command = registered.get('rtsbridge.marineCommand');
assert.equal(command.query({ player: 1, args: { session: sid, request: 1,
    unit_ids: ['openbw:1000'], verb: 'attack', target_id: 'openbw:1001' } }).error, undefined);
command.execute({ player: 1, args: { session: sid, request: 1,
    unit_ids: ['openbw:1000'], verb: 'attack', target_id: 'openbw:1001' } });
drain();
assert.equal(sent.find(m => m.kind === 'combat.command').payload.target_id, 'openbw:1001');
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
    payload: { entities: 5, targets: 3, target_ids: [rideTarget.id, wallTarget.id, sceneryTarget.id], navigation: 'native' } }) + '\n');
assert.ok(actions.filter(a => a.name === 'rtsbridge.targetCatalog').at(-1).args.targets
    .some(target => target.id === rideTarget.id));
const structureArgs = { session: sid, request: 3, unit_ids: ['openbw:1000'],
    verb: 'attack', target_entity_id: rideTarget.id };
assert.equal(command.query({ player: 1, args: structureArgs }).error, undefined);
command.execute({ player: 1, args: structureArgs });
drain();
assert.equal(sent.filter(m => m.kind === 'combat.command').at(-1).payload.target_id, rideTarget.id);
sandbox.network.players.push({ id: 2 });
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
console.log('world plugin discovery and lifecycle validation passed');
