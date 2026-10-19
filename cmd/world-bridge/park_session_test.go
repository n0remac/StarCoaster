package main

import (
	"encoding/json"
	"net"
	"net/http"
	"os"
	"path/filepath"
	"strconv"
	"sync/atomic"
	"testing"

	"starcoaster/internal/world"
)

func TestParkLoadRequiresCommanderCurrentGenerationAndNativeReadiness(t *testing.T) {
	s := defenseService(t)
	path := filepath.Join(os.TempDir(), "sc-park-"+strconv.Itoa(os.Getpid())+".sock")
	_ = os.Remove(path)
	defer os.Remove(path)
	listener, err := net.Listen("unix", path)
	if err != nil {
		t.Fatal(err)
	}
	defer listener.Close()
	var loads atomic.Int32
	backend := &http.Server{Handler: http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/load" {
			loads.Add(1)
			var request parkLoadRequest
			if err := json.NewDecoder(r.Body).Decode(&request); err != nil || request.Park != "B.park" {
				t.Errorf("unexpected load payload: %+v %v", request, err)
			}
			w.WriteHeader(http.StatusAccepted)
		}
		_, _ = w.Write([]byte(`{"phase":"preparing","generation":"generation-a","parks":["A.park","B.park"]}`))
	})}
	go func() { _ = backend.Serve(listener) }()
	defer backend.Close()
	s.parkSupervisorSocket, s.parkGeneration = path, "generation-a"
	request := parkLoadRequest{Park: "B.park", Decision: "discard", Generation: "generation-a",
		PlayerID: 2, CommanderID: 3}
	s.parkLoad(nil, world.Message("park.load.request", s.registry.Session, "unauthorized", "openrct2", 1, request))
	request.CommanderID = 2
	request.Generation = "old-generation"
	s.parkLoad(nil, world.Message("park.load.request", s.registry.Session, "stale", "openrct2", 1, request))
	request.Generation = "generation-a"
	s.ready = false
	s.parkLoad(nil, world.Message("park.load.request", s.registry.Session, "not-ready", "openrct2", 1, request))
	s.ready = true
	s.parkLoad(nil, world.Message("park.load.request", "previous-session", "old-session", "openrct2", 1, request))
	s.parkLoad(nil, world.Message("park.load.request", s.registry.Session, "old-revision", "openrct2", 2, request))
	if loads.Load() != 0 {
		t.Fatal("unready or unauthorized park load reached supervisor")
	}
	s.parkLoad(nil, world.Message("park.load.request", s.registry.Session, "accepted", "openrct2", 1, request))
	if loads.Load() != 1 {
		t.Fatalf("expected one authorized load, got %d", loads.Load())
	}
}

func TestOrdinaryDefenseRejectsDirectMarineSpawn(t *testing.T) {
	s := defenseService(t)
	request := world.SpawnRequest{RequestID: "direct-marine", UnitType: "terran_marine", Count: 1,
		X: 256, Y: 256, Formation: "compact", PlayerID: 2}
	t.Setenv("BRIDGE_ALLOW_DIRECT_SPAWN", "0")
	s.parkMessage(nil, world.Message("unit.spawn.request", s.registry.Session, "direct", "openrct2", 1, request))
	if _, exists := s.spawns.Lookup(request.RequestID); exists {
		t.Fatal("ordinary defense accepted a direct Marine spawn")
	}
}
