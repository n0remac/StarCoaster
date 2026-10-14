/* Test-only native wall route probe. Uses ordinary Marine orders and demolition. */
registerPlugin({ name: "Midway Native Navigation Probe", version: "1.0.0",
    authors: ["StarCoaster"], type: "local", licence: "MIT",
    targetApiVersion: 124, minApiVersion: 124, main: function () {
    if (network.mode !== "client") return;
    var ids = [1000,1001,1002,1003,1004,1005].map(function (n) { return "openbw:"+n; });
    var gate = "openrct2:wall:31:864:960:112:0#1";
    var phase = 0, request = 0, start = 0, last = 0, tick = 0, crossingIds = [];
    function gatePresent() {
        var tile = map.getTile(27,30);
        for (var i=0;i<tile.numElements;i++) {
            var e=tile.getElement(i);
            if (e.type === "wall" && e.direction === 0 && e.object === 31) return true;
        }
        return false;
    }
    function order(session,verb,x,y,target) {
        var args={session:session,request:++request,unit_ids:ids,verb:verb};
        if (target) args.target_entity_id=target; else {args.x=x;args.y=y;}
        context.executeAction("rtsbridge.marineCommand",args,function(result){
            console.log("MIDWAY_NAV_ORDER phase="+phase+" verb="+verb+" accepted="+!result.error+" reason="+(result.errorMessage||"ok"));
        });
        last=Date.now();
    }
    context.subscribe("interval.tick",function(){
        var snap=rtsBridge.getActors();
        if (!snap || !snap.session || !Array.isArray(snap.units)) return;
        var marines=snap.units.filter(function(u){return ids.indexOf(u.id)>=0;});
        if (marines.length!==6) return;
        if (!start) start=Date.now();
        if (++tick%8===0) console.log("MIDWAY_NAV_POSITION phase="+phase+" elapsed="+(Date.now()-start)+" units="+
            marines.map(function(u){return u.id+":"+u.x+","+u.y;}).join(";"));
        if (phase===0 && Date.now()-start>2000) {
            phase=1;order(snap.session,"move",1120,1008);
        } else if (phase===1 && Date.now()-last>13000) {
            phase=2;order(snap.session,"attack",0,0,gate);
        } else if (phase===2 && !gatePresent()) {
            console.log("MIDWAY_NAV_GATE_REMOVED elapsed="+(Date.now()-start));
            phase=3;order(snap.session,"move",720,1008);
        } else if (phase===2 && Date.now()-last>10000) {
            order(snap.session,"attack",0,0,gate);
        } else if (phase===3 && (marines.some(function(u){return u.x<800;}) || Date.now()-last>25000)) {
            crossingIds = marines.filter(function(u){return u.x<864;}).map(function(u){return u.id;});
            phase=4;order(snap.session,"move",1120,1008);
        } else if (phase===4 && crossingIds.length && marines.some(function(u){
            return crossingIds.indexOf(u.id)>=0 && u.x>930 && u.y>900 && u.y<1100;
        })) {
            phase=5;console.log("MIDWAY_NAV_SEQUENCE_COMPLETE elapsed="+(Date.now()-start));
        }
    });
}});
