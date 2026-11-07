const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const messages = [], actions = [];
let interval;
const network = { mode: 'none' };
const workers = Array.from({ length: 4 }, (_, index) => ({
    id: `openbw:${2506 + index}`, kind: 'terran_scv', alive: true,
    x: 1280, y: 1600, z: 112, motion: 'idle',
}));
const sandbox = {
    network,
    rtsBridge: { getActors: () => ({ session: 'ordinary', units: [
        ...workers,
        ...Array.from({ length: 6 }, (_, index) => ({ id: `mineral-${index}`,
            kind: 'mineral_field', alive: true })),
        { id: 'geyser', kind: 'vespene_geyser', alive: true },
    ] }) },
    ui: { mainViewport: { moveTo: () => {} } },
    context: {
        subscribe: (_name, callback) => { interval = callback; },
        executeAction: (_name, args, done) => { actions.push(args); done({ error: false }); },
    },
    console: { log: (message) => messages.push(message) },
    registerPlugin: (plugin) => plugin.main(),
};
vm.runInNewContext(fs.readFileSync('tests/economy_e4_ordinary_browser_probe.js', 'utf8'), sandbox);
assert.equal(typeof interval, 'function', 'title-screen plugin must subscribe before client join');
for (let i = 0; i < 150; i++) interval();
assert.equal(actions.length, 0, 'title screen sent a game command');
network.mode = 'client';
for (let i = 0; i < 150; i++) interval();
assert.equal(actions.filter(action => action.verb === 'train').length, 1);
assert.equal(actions.filter(action => action.verb === 'gather').length, 1);
assert.ok(messages.some(message => message.includes('ECONOMY_E4_CLIENT workers=4 minerals=6 geysers=1')));
console.log('E4 title-to-game economy probe: PASS');
