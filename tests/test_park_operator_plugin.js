const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const joins = [];
const leaves = [];
const assignments = [];
const network = { mode: 'server', currentPlayer: { id: 0 }, players: [{ id: 0 }] };
const context = {
    subscribe(kind, handler) {
        if (kind === 'network.join') joins.push(handler);
        if (kind === 'network.leave') leaves.push(handler);
    },
    executeAction(kind, args, done) {
        assert.equal(kind, 'playersetgroup');
        assignments.push(args);
        done({});
    },
};
vm.runInNewContext(fs.readFileSync('openrct2-plugin/park-operator-permissions.js', 'utf8'), {
    network, context, console, registerPlugin(plugin) { plugin.main(); },
});
assert.equal(joins.length, 1);
assert.equal(leaves.length, 1);
network.players.push({ id: 2 });
joins[0]({ player: 2 });
network.players.push({ id: 3 });
joins[0]({ player: 3 });
assert.deepEqual(JSON.parse(JSON.stringify(assignments)), [{ playerId: 2, groupId: 0 }],
    'the first joined park operator receives construction and management permissions');
network.mode = 'client';
joins[0]({ player: 4 });
assert.equal(assignments.length, 1);
network.mode = 'server';
leaves[0]({ player: 2 });
assert.deepEqual(JSON.parse(JSON.stringify(assignments[1])), { playerId: 3, groupId: 0 },
    'the remaining player becomes park operator when the first leaves');

const host = fs.readFileSync('scripts/run-openrct2-host.sh', 'utf8');
assert.match(host, /cp "\$project_dir\/openrct2-plugin\/park-operator-permissions\.js" "\$server_data\/plugin\/park-operator-permissions\.js"/,
    'the normal host stages operator permissions');
