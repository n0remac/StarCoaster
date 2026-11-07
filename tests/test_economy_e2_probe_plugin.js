const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

// A reconnect can receive the trained worker after the first worker report.
// The probe must wait for that observation and must not issue another order.
const messages = [];
const actions = [];
let interval;
let workerCount = 4;
const sandbox = {
    STARCOASTER_ECONOMY_E2_OBSERVE_ONLY: true,
    network: { mode: 'client' },
    rtsBridge: { getActors: () => ({ session: 'same-session', units:
        Array.from({ length: workerCount }, (_, index) => ({
            id: `openbw:${2506 + index}`, alive: true, kind: 'terran_scv', motion: 'idle',
        })) }) },
    context: {
        subscribe: (_event, callback) => { interval = callback; },
        executeAction: (...args) => actions.push(args),
    },
    ui: { mainViewport: { moveTo: () => {} } },
    console: { log: (message) => messages.push(message) },
    registerPlugin: (plugin) => plugin.main(),
};
vm.runInNewContext(fs.readFileSync('tests/economy_e2_gather_probe.js', 'utf8'), sandbox);
for (let tick = 0; tick < 150; tick++) interval();
workerCount = 5;
for (let tick = 0; tick < 300; tick++) interval();
assert.equal(messages.filter((message) => message === 'ECONOMY_E2_RECONNECTED workers=5').length, 1);
assert.equal(actions.length, 0);
console.log('E2 reconnect worker probe: PASS');
