const assert = require('node:assert/strict');
const crypto = require('node:crypto');
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
assert.equal(open.policy_version, 2);
assert.equal(open.enemy_base.state, 'ready');
assert.deepEqual(findEconomyLayout(park(64, 64), 'source-a').enemy_base, open.enemy_base);
const chosenSides = new Set();
for (let index = 0; index < 16; index++) {
    const seed = crypto.createHash('sha256').update(`park-${index}`).digest('hex').slice(0, 16);
    const [x, y] = findEconomyLayout(park(64, 64), seed).enemy_base.structures[0].tile;
    chosenSides.add(x < 20 ? 'west' : x > 40 ? 'east' : y < 20 ? 'north' : 'south');
}
assert.ok(chosenSides.size >= 3, 'seeded site selection must consider the full perimeter');
assert.deepEqual(open.enemy_base.structures.map(s => s.type),
    ['zerg_hatchery', 'zerg_spawning_pool']);
const economyCells = new Set(open.starting_entities.flatMap(e => {
    const [w, h] = ({terran_command_center: [4, 3], terran_scv: [1, 1],
        mineral_field: [2, 1], vespene_geyser: [4, 2]})[e.type];
    return Array.from({length: w * h}, (_, i) => `${e.tile[0] + i % w}:${e.tile[1] + Math.floor(i / w)}`);
}));
for (const structure of open.enemy_base.structures) {
    const [w, h] = structure.type === 'zerg_hatchery' ? [4, 3] : [3, 2];
    for (let y = structure.tile[1]; y < structure.tile[1] + h; y++)
        for (let x = structure.tile[0]; x < structure.tile[0] + w; x++)
            assert.ok(!economyCells.has(`${x}:${y}`), 'colony overlaps finite economy');
}
assert.ok(open.enemy_base.structures[0].tile[0] <= 13 || open.enemy_base.structures[0].tile[1] <= 13
    || open.enemy_base.structures[0].tile[0] >= 43 || open.enemy_base.structures[0].tile[1] >= 43);
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

const noColony = findEconomyLayout(park(64, 64, (x, y) => ({
    ownership: x >= 14 && x < 50 && y >= 24 && y < 40 ? 2 : 0,
})), 'source-no-colony');
assert.equal(noColony.state, 'ready');
assert.equal(noColony.enemy_base.state, 'blocked');
assert.equal(noColony.enemy_base.reason, 'no_valid_perimeter_site');

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
