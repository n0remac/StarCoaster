const assert = require('node:assert/strict');
const { findEconomyLayout, POLICY_VERSION } = require('../scripts/economy-layout.js');

function park(width, height, cell = () => ({})) {
    return { size: { x: width, y: height }, getTile(x, y) {
        const options = cell(x, y);
        const surface = { type: 'surface', baseHeight: options.height ?? 14,
            slope: options.slope ?? 0, waterHeight: options.water ?? 0,
            ownership: options.ownership ?? 2 };
        const elements = [surface, ...(options.elements || []).map(type => ({ type }))];
        return { numElements: elements.length, getElement: index => elements[index] };
    } };
}

const open = findEconomyLayout(park(64, 64), 'source-a');
assert.equal(open.policy_version, POLICY_VERSION);
assert.equal(open.state, 'ready');
assert.equal(open.starting_entities.filter(entity => entity.type === 'terran_scv').length, 4);
assert.equal(open.starting_entities.filter(entity => entity.type === 'mineral_field').length, 6);
assert.equal(open.starting_entities.filter(entity => entity.type === 'vespene_geyser').length, 1);
assert.equal(open.starting_entities.filter(entity => entity.type === 'terran_command_center').length, 1);
assert.deepEqual(findEconomyLayout(park(64, 64), 'source-a'), open);

const water = findEconomyLayout(park(64, 64, (x, y) => ({
    water: x >= 15 && x < 50 && y >= 15 && y < 50 ? 96 : 0,
})), 'source-b');
assert.equal(water.state, 'blocked');

const crowded = findEconomyLayout(park(64, 64, (x, y) => ({
    elements: x >= 11 && x < 33 && y >= 15 && y < 24 ? [] : ['track'],
})), 'source-c');
assert.equal(crowded.state, 'ready');
assert.ok(crowded.starting_entities.find(entity => entity.id === 'base').tile[0]
    < crowded.starting_entities.find(entity => entity.id === 'mineral-a').tile[0],
    'the native proven mineral approach is to the right of the Command Center');
for (const entity of crowded.starting_entities) {
    assert.ok(entity.tile[0] >= 11 && entity.tile[0] < 33);
    assert.ok(entity.tile[1] >= 15 && entity.tile[1] < 24);
}

const unowned = findEconomyLayout(park(64, 64, () => ({ ownership: 0 })), 'source-d');
assert.equal(unowned.state, 'blocked');
assert.equal(unowned.reason, 'no_native_valid_economy_site');

const splitLevel = findEconomyLayout(park(64, 64, (x, y) => ({
    ownership: x >= 20 && x < 42 && y >= 20 && y < 29 ? 2 : 0,
    height: x < 24 ? 16 : 14,
})), 'source-cliff');
assert.equal(splitLevel.state, 'blocked',
    'a worker can stand next to a raised base but cannot deliver to it');

const large = findEconomyLayout(park(256, 256), 'source-e');
assert.equal(large.state, 'ready');
assert.ok(large.candidates_checked <= 65536 * 4);
assert.ok(large.candidates_retained <= 4096);

console.log('deterministic economy layout and blocked-site validation passed');
