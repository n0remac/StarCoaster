const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const session = 'a'.repeat(32);
const actions = new Map(), animations = [];
const depot = { index: 17, identifier: 'starcoaster.scenery_large.terran_supply_depot' };
const sandbox = {
    map: { size: { x: 64, y: 64 }, getTile() { return { numElements: 1,
        getElement() { return { type: 'surface', baseZ: 112 }; } }; } },
    objectManager: { getAllObjects(kind) { return kind === 'large_scenery' ? [depot] : []; } },
    network: { mode: 'client', currentPlayer: { id: 1 }, players: [{ id: 1 }] },
    rtsBridge: { version: 6, assetVersion: 7, applySnapshot() {}, clearSnapshot() {},
        invalidateAnimation() {}, setBuildingAnimations(value) { animations.push(value); },
        cursorWorld() {}, actorScreenPosition() {} },
    context: { subscribe() {}, registerAction(name, query, execute) {
        actions.set(name, { query, execute });
    } },
    console: { log() {} }, registerPlugin(plugin) { plugin.main(); },
};
vm.runInNewContext(fs.readFileSync('openrct2-plugin/rts-bridge.js', 'utf8'), sandbox);
const execute = (name, args) => {
    const action = actions.get(name), event = { player: 1, args };
    assert.equal(action.query(event).error, undefined, name);
    action.execute(event);
};
execute('rtsbridge.applySnapshot', { session, seq: 1, units: [] });
const intent = { session, intent_id: 'build:1:1', building_type: 'terran_supply_depot',
    tile_x: 10, tile_y: 12, native_id: 'openbw:40', state: 'bound' };
execute('rtsbridge.constructionState', intent);
assert.equal(animations.at(-1).object, depot.index);
assert.equal(animations.at(-1).tiles.length, 6);
assert.equal(animations.at(-1).tiles[0].frame, 1,
    'native intent seeds base plate before park projection and before building/catalog state');
execute('rtsbridge.constructionState', { ...intent, state: 'constructing' });
assert.equal(animations.at(-1).tiles[0].frame, 1);
const building = { session, id: 'openrct2:large_scenery:17:320:384:112:0#1',
    native_id: 'openbw:40', owner: 1, race: 'Terran', completed: false,
    health: 300, max_health: 500, queue: 0, remaining_frames: 0,
    minerals: 0, gas: 0, supply_used: 0, supply_total: 0,
    construction_progress: 70, construction_remaining_frames: 240,
    command_authorized: false, availability: {}, commands: [] };
execute('rtsbridge.buildingState', building);
assert.equal(animations.at(-1).tiles[0].frame, 1,
    'first projected frame remains the base plate even if native progress arrived early');
execute('rtsbridge.constructionState', { ...intent, state: 'constructing',
    projection_id: building.id });
assert.equal(animations.at(-1).tiles[0].frame, 3,
    'native progress advances after projection, before a target catalog arrives');
execute('rtsbridge.buildingState', { ...building, completed: true, construction_progress: 100 });
assert.equal(animations.at(-1).tiles.length, 0,
    'native completion wins even before the construction intent completes');
execute('rtsbridge.buildingState', { ...building, construction_progress: 20 });
assert.equal(animations.at(-1).tiles.length, 0,
    'late incomplete state cannot reopen a native completed building');
execute('rtsbridge.constructionState', { ...intent, state: 'completed' });
assert.equal(animations.at(-1).tiles.length, 0, 'native completion restores idle artwork');
execute('rtsbridge.constructionState', { ...intent, state: 'constructing' });
assert.equal(animations.at(-1).tiles.length, 0, 'late active state cannot reopen completion');
const canceled = { ...intent, intent_id: 'build:1:2', tile_x: 20, state: 'bound' };
execute('rtsbridge.constructionState', canceled);
assert.equal(animations.at(-1).tiles.length, 6);
execute('rtsbridge.constructionState', { ...canceled, state: 'canceled' });
assert.equal(animations.at(-1).tiles.length, 0, 'cancellation removes provisional artwork');
const destroyed = { ...intent, intent_id: 'build:1:3', tile_x: 30, state: 'bound' };
execute('rtsbridge.constructionState', destroyed);
assert.equal(animations.at(-1).tiles.length, 6);
execute('rtsbridge.constructionState', { ...destroyed, state: 'destroyed' });
assert.equal(animations.at(-1).tiles.length, 0, 'destruction removes provisional artwork');
const fast = { ...intent, intent_id: 'build:1:4', tile_x: 40, state: 'completed' };
execute('rtsbridge.constructionState', fast);
assert.equal(animations.at(-1).tiles[0].frame, 1,
    'even a fast native completion starts with the base plate at projection');
execute('rtsbridge.constructionState', { ...fast, projection_id: 'projected:40' });
assert.equal(animations.at(-1).tiles.length, 0,
    'the completed bank becomes visible after the projection is linked');
