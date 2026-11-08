const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

function boot(finite) {
    let query;
    const depot = { index: 17, identifier: 'starcoaster.scenery_large.terran_supply_depot' };
    const base = { id: 'base', type: 'terran_command_center', x: 20, y: 8,
        z: 112, owner: 1 };
    const sandbox = {
        map: { size: { x: 64, y: 64 }, getTile() {
            const surface = { type: 'surface', baseHeight: 14, hasConstructionRights: true };
            return { numElements: 1, getElement() { return surface; } };
        } },
        objectManager: { getAllObjects(kind) {
            return kind === 'large_scenery' ? [depot] : [];
        } },
        network: { mode: 'server', currentPlayer: { id: 1 },
            players: [{ id: 1 }, { id: 2 }], createSocket() {
                return { on() {}, connect() {}, destroy() {} };
            } },
        rtsBridge: { version: 5, assetVersion: 5, cursorWorld() {},
            invalidateAnimation() {}, setBuildingAnimations() {}, applySnapshot() {},
            clearSnapshot() {}, actorScreenPosition() {} },
        context: { getParkStorage() { return { get(key, fallback) {
            if (key === 'economyMode') return finite ? 'finite' : '';
            if (key === 'scenarioStructures') return [base];
            return fallback;
        }, set() {} }; }, subscribe(name, handler) {
            if (name === 'action.query') query = handler;
        }, registerAction() {}, executeAction() {} },
        console: { log() {} }, registerPlugin(plugin) { plugin.main(); },
    };
    vm.runInNewContext(fs.readFileSync('openrct2-plugin/rts-bridge.js', 'utf8'), sandbox);
    return function check(action, args, player = 2) {
        const event = { action, args, player, result: {} };
        query(event);
        return event.result;
    };
}

const finite = boot(true);
assert.equal(finite('largesceneryplace', { x: 34 * 32, y: 10 * 32, object: 17 }).error, 1);
assert.equal(finite('largesceneryremove', { x: 20 * 32, y: 8 * 32 }).error, 1);
assert.equal(finite('clearscenery', { x1: 20 * 32, y1: 8 * 32,
    x2: 24 * 32, y2: 11 * 32 }).error, 1);
assert.equal(finite('largesceneryplace', { x: 34 * 32, y: 10 * 32, object: 99 }).error,
    undefined);
const legacy = boot(false);
assert.equal(legacy('largesceneryplace', { x: 34 * 32, y: 10 * 32, object: 17 }).error,
    undefined);
