const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

function checkPark(size) {
    const actions = new Map(), menu = new Map(), windows = new Map();
    const tiles = new Map(), orders = [];
    let tool, selection;
    const session = 'a'.repeat(32), offset = Math.floor((256 - size) / 2);
    const siteX = 18, siteY = 12, geyserID = 'geyser';
    const geyser = { id: 'openbw:999', kind: 'vespene_geyser', owner: 11,
        x: siteX * 32 + 64, y: siteY * 32 + 32,
        hp: 500, max_hp: 500, facing: 0, motion: 'idle', attack_frames: 0,
        resource_site_id: geyserID };
    const worker = { id: 'openbw:201', kind: 'terran_scv', owner: 1,
        x: 6 * 32, y: 6 * 32, hp: 60, max_hp: 60,
        facing: 0, motion: 'idle', attack_frames: 0 };
    function tile(x, y) {
        const key = `${x},${y}`;
        if (!tiles.has(key)) tiles.set(key, [{ type: 'surface', baseZ: 112,
            slope: 0, waterHeight: 0, hasConstructionRights: true }]);
        const elements = tiles.get(key);
        return { numElements: elements.length, getElement(index) { return elements[index]; }, elements };
    }
    const ui = { tileSelection: {}, get tool() { return tool; },
        registerMenuItem(name, callback) { menu.set(name, callback); },
        registerShortcut() {}, registerViewportInteraction(value) { selection = value; },
        openWindow(desc) { const window = { desc, findWidget(name) {
            return desc.widgets.find(widget => widget.name === name);
        }, bringToFront() {}, close() {} }; windows.set(desc.classification, window); return window; },
        activateTool(value) { tool = value; value.cancel = () => { tool = null; }; },
        showError(_title, message) { throw Error(message); } };
    const context = { subscribe() {}, registerAction(name, query, execute) {
        actions.set(name, { query, execute });
    }, queryAction(_name, _args, callback) { callback({}); },
    executeAction(name, args, callback) {
        if (name === 'rtsbridge.marineCommand') orders.push(args);
        callback({});
    } };
    const sandbox = { map: { size: { x: size, y: size }, getTile: tile },
        objectManager: { getAllObjects() { return [{ index: 7,
            identifier: 'starcoaster.scenery_large.terran_refinery' }]; } },
        network: { mode: 'client', currentPlayer: { id: 1 }, players: [{ id: 1 }] },
        rtsBridge: { version: 5, assetVersion: 6, clearSnapshot() {}, applySnapshot() {},
            invalidateAnimation() {}, setBuildingAnimations() {}, cursorWorld() { return null; },
            actorScreenPosition(id) { return id === worker.id ? { x: 50, y: 50 } : null; } },
        ui, context, console: { log() {} }, registerPlugin(plugin) { plugin.main(); } };
    vm.runInNewContext(fs.readFileSync('openrct2-plugin/rts-bridge.js', 'utf8'), sandbox);
    actions.get('rtsbridge.applySnapshot').execute({ player: 1,
        args: { session, seq: 1, units: [worker, geyser] } });
    actions.get('rtsbridge.scenarioStatus').execute({ player: 1,
        args: { session, scenario_id: 'test', display_name: 'Test', objective: '',
            mode: 'park_defense', finite_economy: true, wave_ordinal: 0,
            wave_total: 0, wave_state: '', outcome: '', error: '' } });
    actions.get('rtsbridge.constructionCatalog').execute({ player: 1,
        args: { session, buildings: [{ building_type: 'terran_refinery', minerals: 100,
            gas: 0, available: true, reason: '', requirement: '' }] } });
    actions.get('rtsbridge.resourceSiteState').execute({ player: 1,
        args: { session, site_id: geyserID, generation: 1, type: 'vespene_geyser',
            lifecycle: 'deposit', x: geyser.x + offset * 32,
            y: geyser.y + offset * 32, owner: 11, amount: 5000,
            publisher_native_id: '200', controller_native_id: '200' } });
    const pick = { screenCoords: { x: 50, y: 50 }, mapCoords: { x: worker.x, y: worker.y } };
    selection.onDown(pick); assert.equal(selection.onUp(pick), true);
    menu.get('StarCraft Construction')();
    const window = windows.get('starcoaster-construction');
    // The construction menu is the same control used by native and browser clients.
    const construction = window.desc.widgets.find(widget =>
        widget.text && widget.text.startsWith('Refinery'));
    construction.onClick();
    const point = (x, y) => ({ mapCoords: { x, y }, screenCoords: { x: 200, y: 200 } });
    const inside = point(siteX * 32 + 70, siteY * 32 + 25);
    tool.onMove(inside);
    assert.match(window.findWidget('barracks-status').text, /Native site ready/);
    tool.onDown(inside);
    assert.equal(orders.length, 1);
    assert.equal(orders[0].geyser_site_id, geyserID);
    assert.equal(orders[0].tile_x, siteX);
    assert.equal(orders[0].tile_y, siteY);
    construction.onClick();
    const outside = point((siteX + 5) * 32, siteY * 32);
    tool.onMove(outside);
    assert.match(window.findWidget('barracks-status').text, /Select the visible geyser/);
    tool.onDown(outside);
    assert.equal(orders.length, 1);

    const blocker = { ...worker, id: 'openbw:202', kind: 'terran_marine',
        x: siteX * 32 + 20, y: siteY * 32 + 20 };
    actions.get('rtsbridge.applySnapshot').execute({ player: 1,
        args: { session, seq: 2, units: [worker, geyser, blocker] } });
    tool.onMove(inside);
    assert.match(window.findWidget('barracks-status').text, /unit occupies/);
    tool.onDown(inside);
    assert.equal(orders.length, 1);
    actions.get('rtsbridge.applySnapshot').execute({ player: 1,
        args: { session, seq: 3, units: [worker, geyser] } });
    actions.get('rtsbridge.constructionState').execute({ player: 1,
        args: { session, intent_id: 'build:1:1', building_type: 'terran_refinery',
            tile_x: siteX, tile_y: siteY, state: 'ordered' } });
    tool.onMove(inside);
    assert.match(window.findWidget('barracks-status').text, /Site already reserved/);
    tool.onDown(inside);
    assert.equal(orders.length, 1);
    actions.get('rtsbridge.constructionState').execute({ player: 1,
        args: { session, intent_id: 'build:1:1', state: 'canceled' } });
    tile(siteX, siteY).elements[0].hasConstructionRights = false;
    tool.onMove(inside);
    assert.match(window.findWidget('barracks-status').text, /construction rights/);
    tool.onDown(inside);
    assert.equal(orders.length, 1);
    tile(siteX, siteY).elements[0].hasConstructionRights = true;
    actions.get('rtsbridge.resourceSiteState').execute({ player: 1,
        args: { session, site_id: geyserID, generation: 2, type: 'terran_refinery',
            lifecycle: 'refinery', x: geyser.x + offset * 32,
            y: geyser.y + offset * 32, owner: 1, amount: 5000,
            publisher_native_id: '200', controller_native_id: '200' } });
    tool.onMove(inside);
    assert.match(window.findWidget('barracks-status').text, /Select the visible geyser/);
    actions.get('rtsbridge.resourceSiteState').execute({ player: 1,
        args: { session, site_id: geyserID, generation: 3, type: 'vespene_geyser',
            lifecycle: 'deposit', x: geyser.x + offset * 32,
            y: geyser.y + offset * 32, owner: 11, amount: 5000,
            publisher_native_id: '201', controller_native_id: '201' } });
    tool.onMove(inside);
    assert.match(window.findWidget('barracks-status').text, /Native site ready/);
}

checkPark(64);
checkPark(128);
checkPark(256);
