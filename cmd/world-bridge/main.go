package main

import (
	"bufio"
	"encoding/hex"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"log"
	"net"
	"os"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"sync"
	"time"

	"starcoaster/internal/world"
)

type peer struct {
	net.Conn
	mu sync.Mutex
}

func (p *peer) send(m world.Envelope) error {
	p.mu.Lock()
	defer p.mu.Unlock()
	_ = p.SetWriteDeadline(time.Now().Add(5 * time.Second))
	return json.NewEncoder(p.Conn).Encode(m)
}

type staging struct {
	session  string
	revision uint64
	begin    world.SnapshotBegin
	entities []world.Entity
	terrain  []world.Terrain
	chunks   int
	seen     map[string]bool
}
type service struct {
	mu                        sync.Mutex
	park, bw                  *peer
	controller                *peer
	registry                  *world.Registry
	actors                    *world.ActorRegistry
	mapping                   world.Mapping
	stage                     *staging
	parkPatch                 *parkPatchStage
	next                      uint64
	pending                   map[string]world.CombatEvent
	pendingFrames             map[string]int
	proxies                   map[string]string
	targetLinks               map[string]targetLink
	pendingLinks              map[string]string
	pendingReady              *world.Ready
	lastReady                 *world.Ready
	startedSession            string
	navigationMask            world.NavigationMask
	navigationRevision        uint64
	navigationStarted         time.Time
	navigationMeasured        bool
	publisherNavigationReady  bool
	controllerNavigationReady bool
	ready                     bool
	bwResyncPending           bool
	bwWidth                   int
	bwHeight                  int
	transform                 world.Transform
	scenario                  *world.Scenario
	runtime                   *world.ScenarioRuntime
	objectiveID               string
	outcome                   string
	lastMarines               int
	lastZerglings             int
	nativeOccupants           []world.NativeOccupant
	nativeOccupancyComplete   bool
	actorReconcileComplete    bool
	reconciledActors          map[string]bool
	retired                   map[string]bool
	commands                  map[string]worldCommand
	spawns                    *world.SpawnQueue
	spawnOps                  map[string]world.SpawnExecute
	spawnJournalPath          string
	maxLiveActors             int
	lastScenarioStatus        string
}

type parkPatchStage struct {
	patch     world.Patch
	digest    string
	candidate *world.Registry
	mask      world.NavigationMask
	created   time.Time
}

type worldCommand struct {
	CommandID     string   `json:"command_id"`
	PlayerID      int      `json:"player_id"`
	RequestID     int      `json:"request_id"`
	UnitIDs       []string `json:"unit_ids"`
	Verb          string   `json:"verb"`
	TargetID      string   `json:"target_id,omitempty"`
	TargetProxyID string   `json:"target_proxy_id,omitempty"`
	X             int      `json:"x,omitempty"`
	Y             int      `json:"y,omitempty"`
}

type targetLink struct {
	ID      string `json:"id"`
	ProxyID string `json:"proxy_id"`
	X       int    `json:"proxy_x"`
	Y       int    `json:"proxy_y"`
}

func (s *service) sendTargetLinks(p *peer) {
	for _, link := range s.targetLinks {
		s.sendTargetLink(p, s.registry.Session, s.registry.Revision, link)
	}
}

func (s *service) sendControllerNavigation(p *peer) {
	if p == nil || s.registry.Session == "" || s.bwWidth < 1 || s.bwHeight < 1 {
		return
	}
	s.sendNavigationMask(p, 0)
}

func (s *service) refreshNavigationMask() error {
	mask, err := world.DeriveNavigation(s.registry, s.transform, s.bwWidth, s.bwHeight)
	if err != nil {
		return err
	}
	if s.navigationRevision != s.registry.Revision || s.navigationMask.Hash != mask.Hash {
		s.publisherNavigationReady = false
		s.controllerNavigationReady = false
		s.navigationStarted = time.Now()
		s.navigationMeasured = false
	}
	s.navigationMask = mask
	s.navigationRevision = s.registry.Revision
	return nil
}

func (s *service) sendNavigationMask(p *peer, applyFrame int) {
	if p == nil || s.registry.Session == "" || s.bwWidth < 1 || s.bwHeight < 1 {
		return
	}
	if err := s.refreshNavigationMask(); err != nil {
		s.ready = false
		log.Printf("navigation derivation rejected: %v", err)
		_ = s.emit(s.park, "world.error", s.registry.Session, s.registry.Revision,
			map[string]string{"reason": err.Error()})
		return
	}
	const bytesPerChunk = 6000
	chunks := (len(s.navigationMask.Bits) + bytesPerChunk - 1) / bytesPerChunk
	if err := s.emit(p, "navigation.mask.begin", s.registry.Session, s.registry.Revision,
		map[string]any{"width": s.bwWidth, "height": s.bwHeight, "chunks": chunks,
			"hash": s.navigationMask.Hash, "apply_frame": applyFrame}); err != nil {
		log.Printf("navigation begin: %v", err)
		return
	}
	for index, start := 0, 0; start < len(s.navigationMask.Bits); index, start = index+1, start+bytesPerChunk {
		end := start + bytesPerChunk
		if end > len(s.navigationMask.Bits) {
			end = len(s.navigationMask.Bits)
		}
		if err := s.emit(p, "navigation.mask.chunk", s.registry.Session, s.registry.Revision,
			map[string]any{"index": index, "hex": hex.EncodeToString(s.navigationMask.Bits[start:end])}); err != nil {
			log.Printf("navigation chunk: %v", err)
			return
		}
	}
	if err := s.emit(p, "navigation.mask.end", s.registry.Session, s.registry.Revision,
		map[string]string{"hash": s.navigationMask.Hash}); err != nil {
		log.Printf("navigation end: %v", err)
	}
}

func (s *service) sendTargetLink(p *peer, session string, revision uint64, link targetLink) {
	if p == nil {
		return
	}
	opID := s.operation()
	if p.send(world.Message("entity.state", session, opID, "bridge", revision, link)) == nil {
		if s.pendingLinks == nil {
			s.pendingLinks = map[string]string{}
		}
		s.pendingLinks[opID] = link.ID
	}
}

func (s *service) publishReady() {
	if s.publisherNavigationReady && s.controllerNavigationReady &&
		!s.navigationMeasured && !s.navigationStarted.IsZero() {
		log.Printf("navigation initialized hash=%s elapsed_ms=%d", s.navigationMask.Hash,
			time.Since(s.navigationStarted).Milliseconds())
		s.navigationMeasured = true
	}
	if s.pendingReady == nil || s.controller == nil || !s.publisherNavigationReady || !s.controllerNavigationReady || len(s.pendingLinks) != 0 {
		return
	}
	if s.scenario != nil && s.scenario.Version == 2 && !s.actorReconcileComplete {
		return
	}
	ready := *s.pendingReady
	s.pendingReady = nil
	ready.TargetIDs = make([]string, 0, len(s.proxies))
	for id := range s.proxies {
		if !s.registry.Destroyed[id] {
			ready.TargetIDs = append(ready.TargetIDs, id)
		}
	}
	sort.Strings(ready.TargetIDs)
	if err := s.initScenarioRuntime(); err != nil {
		s.ready = false
		log.Printf("scenario %s cannot start: %v", s.scenario.ID, err)
		_ = s.emit(s.park, "world.error", s.registry.Session, s.registry.Revision, map[string]string{"reason": err.Error()})
		return
	}
	if s.scenario != nil {
		runtimeMarines, runtimeZerglings := 0, 0
		if s.actors != nil {
			for _, actor := range s.actors.Living() {
				if actor.Type == "terran_marine" {
					runtimeMarines++
				}
				if actor.Type == "zerg_zergling" {
					runtimeZerglings++
				}
			}
		}
		destroyed := s.runtime != nil && s.runtime.ObjectiveDestroyed && s.runtime.Outcome == "defeat"
		if err := s.scenario.CheckReadyWithRuntimeState(s.registry, s.proxies, ready,
			runtimeMarines, runtimeZerglings, destroyed); err != nil {
			s.ready = false
			log.Printf("scenario %s cannot start: %v", s.scenario.ID, err)
			_ = s.emit(s.park, "world.error", s.registry.Session, s.registry.Revision,
				map[string]string{"reason": err.Error()})
			return
		}
	}
	if s.runtime != nil {
		s.outcome = s.runtime.Outcome
	}
	s.ready = true
	if s.scenario != nil && s.startedSession != s.registry.Session && s.outcome == "" {
		_ = s.emit(s.bw, "world.start", s.registry.Session, s.registry.Revision,
			map[string]any{"scenario_id": s.scenario.ID, "delay_frames": s.scenario.InitialAI.DelayFrames})
		s.startedSession = s.registry.Session
	}
	_ = s.emit(s.park, "world.ready", s.registry.Session, s.registry.Revision, ready)
	s.publishScenarioStatus(true)
	log.Printf("OpenBW ready targets=%d unsupported=%d", ready.Targets, ready.UnsupportedTotal)
	if s.scenario == nil || s.scenario.Version == 1 {
		s.submitScenarioSpawns()
	}
	s.reconcileUncertainSpawn()
	s.pumpSpawns()
}

func (s *service) announceOutcome(marines, zerglings int) {
	if s.scenario == nil || s.outcome != "" || s.objectiveID == "" || !s.ready {
		return
	}
	state := s.scenario.Outcome(s.registry.Destroyed[s.objectiveID], marines, zerglings)
	if s.runtime != nil && state == "victory" {
		if !s.runtime.AllWavesCleared() || s.spawns == nil || s.spawns.PendingCount() != 0 {
			state = ""
		}
	}
	if state == "" {
		return
	}
	s.outcome = state
	if s.runtime != nil {
		s.runtime.Outcome = state
		if !s.saveScenarioRuntime() {
			s.scenarioRuntimeError(fmt.Errorf("scenario_journal_unavailable"))
			return
		}
	}
	_ = s.emit(s.park, "world.outcome", s.registry.Session, s.registry.Revision,
		map[string]any{"scenario_id": s.scenario.ID, "state": state,
			"objective_id": s.objectiveID, "marines": marines, "zerglings": zerglings})
	log.Printf("scenario %s outcome=%s marines=%d zerglings=%d", s.scenario.ID, state, marines, zerglings)
	s.publishScenarioStatus(true)
}

func (s *service) failCommands(reason string) {
	for _, command := range s.commands {
		_ = s.emit(s.park, "combat.result", s.registry.Session, s.registry.Revision,
			map[string]any{"command_id": command.CommandID, "player_id": command.PlayerID,
				"request_id": command.RequestID, "accepted": false, "reason": reason})
	}
	s.commands = map[string]worldCommand{}
}

var unitIDPattern = regexp.MustCompile(`^openbw:[0-9]+$`)

func (s *service) operation() string { s.next++; return fmt.Sprintf("bridge:%d", s.next) }
func (s *service) emit(p *peer, kind, session string, rev uint64, payload any) error {
	if p == nil {
		return fmt.Errorf("peer disconnected")
	}
	return p.send(world.Message(kind, session, s.operation(), "bridge", rev, payload))
}
func (s *service) ack(p *peer, m world.Envelope, accepted bool, reason string) {
	if p == nil {
		return
	}
	_ = p.send(world.Message("world.ack", m.Session, s.operation(), "bridge", m.Revision, world.Ack{OpID: m.OpID, Accepted: accepted, Error: reason}))
}
func (s *service) consume(role string, p *peer) {
	scanner := bufio.NewScanner(p.Conn)
	scanner.Buffer(make([]byte, 4096), 1048576)
	for scanner.Scan() {
		var m world.Envelope
		if err := json.Unmarshal(scanner.Bytes(), &m); err != nil {
			log.Printf("%s malformed JSON: %v", role, err)
			continue
		}
		if err := m.Validate(); err != nil {
			log.Printf("%s invalid %s: %v", role, m.Kind, err)
			s.mu.Lock()
			s.ack(p, m, false, err.Error())
			s.mu.Unlock()
			continue
		}
		s.mu.Lock()
		if (role == "park" && s.park == p) || (role == "bw" && s.bw == p) ||
			(role == "controller" && s.controller == p) {
			s.handle(role, p, m)
		}
		s.mu.Unlock()
	}
	s.mu.Lock()
	if role == "park" && s.park == p {
		s.park = nil
		s.stage = nil
	}
	if role == "bw" && s.bw == p {
		s.bw = nil
		s.ready = false
		s.nativeOccupancyComplete = false
		s.actorReconcileComplete = false
		if s.spawns != nil {
			if status, ok := s.spawns.Uncertain(); ok {
				s.saveSpawns()
				s.spawnStatus(status)
			}
		}
		if s.actors != nil {
			s.actors.UnbindParticipant("publisher")
		}
	}
	if role == "controller" && s.controller == p {
		s.controller = nil
		if s.actors != nil {
			s.actors.UnbindParticipant("controller")
		}
		s.controllerNavigationReady = false
		s.ready = false
		if s.lastReady != nil {
			copyReady := *s.lastReady
			s.pendingReady = &copyReady
		}
		s.pendingLinks = map[string]string{}
		s.failCommands("controller_disconnected")
	}
	s.mu.Unlock()
	_ = p.Close()
	log.Printf("%s disconnected: %v", role, scanner.Err())
}
func (s *service) handle(role string, p *peer, m world.Envelope) {
	if role == "park" {
		s.parkMessage(p, m)
	} else if role == "bw" {
		s.bwMessage(p, m)
	} else {
		s.controllerMessage(p, m)
	}
}
func (s *service) parkMessage(p *peer, m world.Envelope) {
	if m.Source != "openrct2" {
		s.ack(p, m, false, "wrong_authority")
		return
	}
	switch m.Kind {
	case "world.hello":
		s.ack(p, m, true, "")
	case "world.snapshot.begin":
		if s.retired[m.Session] || (s.registry.Session == m.Session && m.Revision < s.registry.Revision) {
			s.ack(p, m, false, "stale_world")
			return
		}
		var b world.SnapshotBegin
		if m.Decode(&b) != nil || b.Width < 1 || b.Height < 1 || b.Width > 1024 || b.Height > 1024 || b.Chunks < 1 || b.Chunks > 100000 {
			s.ack(p, m, false, "invalid_snapshot_begin")
			return
		}
		s.stage = &staging{session: m.Session, revision: m.Revision, begin: b, seen: map[string]bool{}}
		s.parkPatch = nil
		s.ready = false
		s.ack(p, m, true, "")
	case "world.snapshot.chunk":
		if s.stage != nil && s.stage.seen[m.OpID] {
			s.ack(p, m, true, "")
			return
		}
		if s.stage == nil || s.stage.session != m.Session || s.stage.revision != m.Revision || s.stage.chunks >= s.stage.begin.Chunks {
			s.ack(p, m, false, "unexpected_chunk")
			return
		}
		var c world.SnapshotChunk
		if m.Decode(&c) != nil || c.Index != s.stage.chunks || len(c.Entities) > 64 || len(c.Terrain) > 512 {
			s.ack(p, m, false, "invalid_chunk")
			return
		}
		for _, e := range c.Entities {
			if err := e.Validate(s.stage.begin.Width, s.stage.begin.Height); err != nil {
				s.ack(p, m, false, fmt.Sprintf("%s: %v (cells=%d rects=%d)", e.ID, err, len(e.Geometry.Cells), len(e.Geometry.Rects)))
				return
			}
			s.stage.entities = append(s.stage.entities, s.mapping.Apply(e))
		}
		s.stage.terrain = append(s.stage.terrain, c.Terrain...)
		s.stage.chunks++
		s.stage.seen[m.OpID] = true
		s.ack(p, m, true, "")
	case "world.snapshot.end":
		var end world.SnapshotEnd
		if m.Decode(&end) != nil || s.stage == nil || s.stage.session != m.Session || s.stage.revision != m.Revision || s.stage.chunks != s.stage.begin.Chunks || end.Entities != len(s.stage.entities) || end.Terrain != len(s.stage.terrain) {
			s.ack(p, m, false, "incomplete_snapshot")
			return
		}
		previousSession := s.registry.Session
		s.failCommands("world_resynchronized")
		if err := s.registry.Replace(m.Session, m.Revision, s.stage.begin.Width, s.stage.begin.Height, s.stage.entities, s.stage.terrain); err != nil {
			s.ack(p, m, false, err.Error())
			return
		}
		if previousSession != "" && previousSession != m.Session {
			if s.retired == nil {
				s.retired = map[string]bool{}
			}
			s.retired[previousSession] = true
		}
		if s.actors == nil || s.actors.Session != m.Session {
			s.actors = world.NewActorRegistry(m.Session)
		}
		s.initSpawns(m.Session)
		s.stage = nil
		s.pending = map[string]world.CombatEvent{}
		s.pendingFrames = map[string]int{}
		s.proxies = map[string]string{}
		s.targetLinks = map[string]targetLink{}
		s.pendingLinks = map[string]string{}
		s.pendingReady = nil
		s.lastReady = nil
		s.nativeOccupancyComplete = false
		s.actorReconcileComplete = false
		s.reconciledActors = nil
		if previousSession != m.Session {
			s.outcome = ""
			s.runtime = nil
			s.startedSession = ""
			s.lastMarines = 0
			s.lastZerglings = 0
			s.lastScenarioStatus = ""
		}
		s.navigationMask = world.NavigationMask{}
		s.navigationRevision = 0
		s.publisherNavigationReady = false
		s.controllerNavigationReady = false
		s.ack(p, m, true, "")
		log.Printf("park snapshot session=%s revision=%d entities=%d terrain=%d", m.Session, m.Revision, len(s.registry.Entities), len(s.registry.Terrain))
		s.forwardSnapshot()
		s.sendNavigationMask(s.bw, 0)
		_ = s.emit(s.controller, "world.hello", m.Session, m.Revision, map[string]any{"role": "controller"})
		s.sendControllerNavigation(s.controller)
	case "world.patch":
		var patch world.Patch
		if m.Decode(&patch) != nil || patch.ResultRevision != m.Revision {
			s.ack(p, m, false, "invalid_patch")
			return
		}
		if s.parkPatch != nil {
			if time.Since(s.parkPatch.created) > 30*time.Second {
				log.Printf("park patch expired id=%s", s.parkPatch.patch.ID)
				_ = s.emit(p, "world.patch.status", m.Session, s.parkPatch.patch.ResultRevision,
					map[string]any{"patch_id": s.parkPatch.patch.ID, "state": "failed", "reason": "staging_expired"})
				s.parkPatch = nil
			} else if s.parkPatch.patch.ID == patch.ID && s.parkPatch.digest == patch.Digest() {
				s.ack(p, m, true, "")
				_ = s.emit(p, "world.patch.status", m.Session, m.Revision,
					map[string]any{"patch_id": patch.ID, "state": "staged", "navigation_hash": s.parkPatch.mask.Hash})
				return
			} else {
				s.ack(p, m, false, "patch_in_progress")
				return
			}
		}
		if s.bwWidth == 0 || s.bwHeight == 0 {
			s.ack(p, m, false, "native_dimensions_unavailable")
			return
		}
		candidate, mask, err := s.registry.StagePatch(m.Session, patch, s.mapping,
			s.transform, s.bwWidth, s.bwHeight)
		if err != nil {
			if errors.Is(err, world.ErrPatchDuplicate) {
				s.ack(p, m, true, "")
				_ = s.emit(p, "world.patch.status", m.Session, m.Revision,
					map[string]any{"patch_id": patch.ID, "state": "synchronized",
						"navigation_hash": s.navigationMask.Hash})
				return
			}
			s.ack(p, m, false, err.Error())
			return
		}
		s.parkPatch = &parkPatchStage{patch: patch, digest: patch.Digest(),
			candidate: candidate, mask: mask, created: time.Now()}
		s.ready = false
		s.ack(p, m, true, "")
		_ = s.emit(p, "world.patch.status", m.Session, m.Revision,
			map[string]any{"patch_id": patch.ID, "state": "staged", "navigation_hash": mask.Hash})
		log.Printf("park patch staged id=%s base=%d result=%d hash=%s", patch.ID,
			patch.BaseRevision, patch.ResultRevision, mask.Hash)
	case "world.patch.query":
		var query struct {
			PatchID string `json:"patch_id"`
		}
		if m.Decode(&query) != nil || query.PatchID == "" || m.Session != s.registry.Session {
			s.ack(p, m, false, "invalid_patch_query")
			return
		}
		s.ack(p, m, true, "")
		state, reason, hash := "failed", "unknown_or_expired_patch", ""
		if s.parkPatch != nil && s.parkPatch.patch.ID == query.PatchID {
			if time.Since(s.parkPatch.created) > 30*time.Second {
				s.parkPatch = nil
				s.ready = false
			} else {
				state, reason, hash = "staged", "", s.parkPatch.mask.Hash
			}
		} else if s.registry.AppliedPatches[query.PatchID] != "" {
			state, reason, hash = "synchronized", "", s.navigationMask.Hash
		}
		status := map[string]any{"patch_id": query.PatchID, "state": state, "reason": reason}
		if hash != "" {
			status["navigation_hash"] = hash
		}
		_ = s.emit(p, "world.patch.status", m.Session, m.Revision, status)
	case "combat.result":
		if s.parkPatch != nil {
			s.ready = false
			log.Printf("combat demolition interrupted staged park patch id=%s", s.parkPatch.patch.ID)
			s.parkPatch = nil
			s.ack(p, m, false, "patch_interrupted_by_combat")
			_ = s.emit(p, "world.resync", s.registry.Session, s.registry.Revision,
				map[string]string{"reason": "patch_interrupted_by_combat"})
			return
		}
		var result world.CombatResult
		if m.Decode(&result) != nil {
			s.ack(p, m, false, "invalid_result")
			return
		}
		event, ok := s.pending[result.EventID]
		if !ok || result.EntityID != event.EntityID || m.Session != s.registry.Session {
			s.ack(p, m, false, "unknown_event")
			return
		}
		if result.State != "removal_confirmed" && result.State != "removal_failed" {
			s.ack(p, m, false, "invalid_result_state")
			return
		}
		if result.State == "removal_failed" && m.Revision != s.registry.Revision {
			s.ack(p, m, false, "out_of_order_revision")
			return
		}
		if result.State == "removal_confirmed" {
			if m.Revision != s.registry.Revision+1 {
				s.ack(p, m, false, "out_of_order_revision")
				return
			}
			s.registry.Destroyed[result.EntityID] = true
			if s.runtime != nil && result.EntityID == s.objectiveID {
				s.runtime.ObjectiveDestroyed = true
				if !s.saveScenarioRuntime() {
					s.scenarioRuntimeError(fmt.Errorf("scenario_journal_unavailable"))
					return
				}
			}
			s.registry.Revision = m.Revision
			delete(s.targetLinks, result.EntityID)
			_ = s.emit(s.controller, "entity.remove", m.Session, m.Revision, map[string]string{"id": result.EntityID})
			_ = s.emit(s.park, "entity.remove", m.Session, m.Revision, map[string]string{"id": result.EntityID})
		}
		s.registry.RemovalState[result.EntityID] = result.State
		delete(s.pending, result.EventID)
		s.ack(p, m, true, "")
		_ = s.emit(s.bw, "combat.result", m.Session, s.registry.Revision, result)
		if result.State == "removal_confirmed" {
			// Both OpenBW players must rebuild paths on the same simulation frame.
			// A local update on only one frame diverges their unit positions.
			applyFrame := s.pendingFrames[result.EventID] + 96
			s.sendNavigationMask(s.bw, applyFrame)
			s.sendNavigationMask(s.controller, applyFrame)
			if result.EntityID == s.objectiveID {
				s.announceOutcome(s.lastMarines, s.lastZerglings)
			}
		} else {
			s.ready = false
			_ = s.emit(s.park, "world.resync", m.Session, s.registry.Revision, map[string]string{"reason": "removal_failed"})
		}
		delete(s.pendingFrames, result.EventID)
	case "entity.upsert", "entity.remove", "entity.transform", "entity.state", "navigation.terrain.update":
		// The envelope and model are versioned for future live updates. Applying
		// one side before OpenBW accepts its geometry would split authority.
		s.ack(p, m, false, "live_update_unsupported")
	case "unit.spawn.request", "unit.spawn.query", "unit.spawn.cancel":
		s.parkSpawnMessage(p, m)
	case "combat.command":
		var command worldCommand
		if m.Decode(&command) != nil || m.Session != s.registry.Session || m.Revision != s.registry.Revision ||
			!s.ready || s.outcome != "" || s.controller == nil || command.CommandID == "" || len(command.CommandID) > 128 ||
			command.PlayerID < 0 || command.RequestID < 1 || len(command.UnitIDs) < 1 ||
			len(command.UnitIDs) > 32 || s.commands[command.CommandID].CommandID != "" {
			s.ack(p, m, false, "invalid_or_unavailable_command")
			return
		}
		for _, id := range command.UnitIDs {
			if !unitIDPattern.MatchString(id) {
				s.ack(p, m, false, "invalid_unit_id")
				return
			}
			if s.actors != nil {
				numeric, _ := strconv.Atoi(id[7:])
				_, known := s.actors.Lookup(id)
				if (numeric >= 3000 || known) && !s.actors.Commandable(id) {
					s.ack(p, m, false, "actor_not_bound")
					return
				}
			}
		}
		switch command.Verb {
		case "unit.move", "unit.attack_move":
			if command.X < 0 || command.Y < 0 || command.X >= s.registry.Width*32 || command.Y >= s.registry.Height*32 {
				s.ack(p, m, false, "invalid_destination")
				return
			}
			command.X = s.transform.X(command.X)
			command.Y = s.transform.Y(command.Y)
		case "unit.attack":
			if proxy := s.proxies[command.TargetID]; proxy != "" && !s.registry.Destroyed[command.TargetID] {
				command.TargetProxyID = proxy
			} else if unitIDPattern.MatchString(command.TargetID) {
				command.TargetProxyID = command.TargetID
			} else {
				s.ack(p, m, false, "unknown_target")
				return
			}
		case "unit.hold", "unit.stop":
		default:
			s.ack(p, m, false, "unsupported_command")
			return
		}
		if s.commands == nil {
			s.commands = map[string]worldCommand{}
		}
		if err := s.emit(s.controller, "combat.command", m.Session, m.Revision, command); err != nil {
			s.ack(p, m, false, "controller_disconnected")
			return
		}
		s.commands[command.CommandID] = command
		s.ack(p, m, true, "")
	default:
		s.ack(p, m, false, "unsupported_operation")
	}
}
func (s *service) forwardSnapshot() {
	if s.bw == nil || s.registry.Session == "" {
		return
	}
	if err := s.initScenarioRuntime(); err != nil {
		log.Printf("scenario snapshot rejected: %v", err)
		_ = s.emit(s.park, "world.error", s.registry.Session, s.registry.Revision, map[string]string{"reason": err.Error()})
		return
	}
	r := s.registry
	s.bwResyncPending = false
	rev := r.Revision
	transform, err := world.Fit(r.Width, r.Height, s.bwWidth, s.bwHeight)
	if err != nil {
		log.Printf("OpenBW snapshot rejected: %v", err)
		return
	}
	s.transform = transform
	derivedTerrain := s.transform.Terrain(r.Terrain)
	derivedWidth, derivedHeight := r.Width, r.Height
	if s.bwWidth > 0 && s.bwHeight > 0 {
		derivedWidth = s.bwWidth
		derivedHeight = s.bwHeight
	}
	ids := r.IDs()
	chunks := make([]world.SnapshotChunk, 0, len(ids)/16+len(r.Terrain)/128+1)
	entityChunk := world.SnapshotChunk{}
	for _, id := range ids {
		derived := s.transform.Entity(r.Entities[id])
		next := append(entityChunk.Entities, derived)
		encoded, _ := json.Marshal(next)
		if len(entityChunk.Entities) > 0 && (len(next) > 32 || len(encoded) > 48000) {
			chunks = append(chunks, entityChunk)
			entityChunk = world.SnapshotChunk{Entities: []world.Entity{derived}}
		} else {
			entityChunk.Entities = next
		}
	}
	if len(entityChunk.Entities) > 0 {
		chunks = append(chunks, entityChunk)
	}
	for start := 0; start < len(derivedTerrain); start += 128 {
		end := start + 128
		if end > len(derivedTerrain) {
			end = len(derivedTerrain)
		}
		chunks = append(chunks, world.SnapshotChunk{Terrain: derivedTerrain[start:end]})
	}
	begin := world.SnapshotBegin{Width: derivedWidth, Height: derivedHeight, Chunks: len(chunks)}
	if s.scenario != nil {
		if s.runtime != nil && s.runtime.ObjectiveDestroyed {
			s.objectiveID = s.runtime.ObjectiveEntityID
		} else {
			id, err := s.scenario.ObjectiveEntityID(r, s.scenario.InitialAI.Objective)
			if err != nil {
				log.Printf("scenario objective: %v", err)
			} else if s.runtime != nil && s.runtime.ObjectiveEntityID != "" && s.runtime.ObjectiveEntityID != id {
				s.scenarioRuntimeError(fmt.Errorf("objective_binding_changed: %s to %s", s.runtime.ObjectiveEntityID, id))
				return
			} else {
				begin.ObjectiveID = id
				s.objectiveID = id
				if s.runtime != nil && s.runtime.ObjectiveEntityID == "" {
					s.runtime.ObjectiveEntityID = id
					if !s.saveScenarioRuntime() {
						s.scenarioRuntimeError(fmt.Errorf("scenario_journal_unavailable"))
						return
					}
				}
			}
		}
	}
	if err := s.emit(s.bw, "world.snapshot.begin", r.Session, rev, begin); err != nil {
		log.Printf("OpenBW begin: %v", err)
		return
	}
	for index, chunk := range chunks {
		chunk.Index = index
		if err := s.emit(s.bw, "world.snapshot.chunk", r.Session, rev, chunk); err != nil {
			log.Printf("OpenBW chunk: %v", err)
			return
		}
	}
	_ = s.emit(s.bw, "world.snapshot.end", r.Session, rev, world.SnapshotEnd{Entities: len(r.Entities), Terrain: len(derivedTerrain)})
}
func (s *service) bwMessage(p *peer, m world.Envelope) {
	if m.Source != "openbw" {
		s.ack(p, m, false, "wrong_authority")
		return
	}
	switch m.Kind {
	case "actor.spawn":
		var identity world.ActorIdentity
		if s.actors == nil || m.Session != s.registry.Session ||
			m.Revision != s.registry.Revision || m.Decode(&identity) != nil ||
			s.actors.Spawn(identity) != nil {
			s.ack(p, m, false, "invalid_actor_spawn")
			return
		}
		s.ack(p, m, true, "")
		log.Printf("actor spawn id=%s generation=%d", identity.ID, identity.Generation)
		if s.reconciledActors != nil {
			s.reconciledActors[identity.ID] = true
		}
		_ = s.emit(s.controller, "actor.spawn", m.Session, m.Revision, identity)
	case "actor.reconcile":
		var state world.ActorReconcile
		if s.actors == nil || m.Session != s.registry.Session ||
			m.Revision != s.registry.Revision || m.Decode(&state) != nil {
			s.ack(p, m, false, "invalid_actor_reconciliation")
			return
		}
		previous := s.actors.Living()
		if s.actors.Reconcile(m.Session, state.Living) != nil {
			s.ack(p, m, false, "invalid_actor_reconciliation")
			return
		}
		s.ack(p, m, true, "")
		log.Printf("actor reconcile living=%d", len(state.Living))
		s.actorReconcileComplete = true
		s.reconciledActors = make(map[string]bool, len(state.Living))
		for _, identity := range state.Living {
			s.reconciledActors[identity.ID] = true
		}
		for _, identity := range previous {
			if record, found := s.actors.Lookup(identity.ID); found && record.State == world.ActorRemoved {
				event := world.ActorDespawn{ID: identity.ID, Session: m.Session, Generation: identity.Generation}
				_ = s.emit(s.controller, "actor.despawn", m.Session, m.Revision, event)
				_ = s.emit(s.park, "actor.despawn", m.Session, m.Revision, event)
			}
		}
		for _, identity := range s.actors.Living() {
			_ = s.emit(s.controller, "actor.spawn", m.Session, m.Revision, identity)
		}
		s.publishReady()
	case "actor.bind":
		var binding world.ActorBinding
		if s.actors == nil || m.Session != s.registry.Session ||
			m.Revision != s.registry.Revision || m.Decode(&binding) != nil ||
			binding.Participant != "publisher" || s.actors.Bind(binding) != nil {
			s.ack(p, m, false, "invalid_actor_binding")
			return
		}
		s.ack(p, m, true, "")
		log.Printf("actor binding id=%s participant=publisher native=%s active=%t", binding.ID,
			binding.NativeID, s.actors.Commandable(binding.ID))
		_ = s.emit(s.controller, "actor.bind", m.Session, m.Revision, binding)
		if s.actors.Commandable(binding.ID) {
			_ = s.emit(s.park, "actor.bind", m.Session, m.Revision, binding)
			s.spawnActorReady(binding.ID)
		}
	case "unit.spawn.status":
		s.bwSpawnMessage(p, m)
	case "actor.despawn":
		var event world.ActorDespawn
		if s.actors == nil || m.Session != s.registry.Session ||
			m.Revision != s.registry.Revision || m.Decode(&event) != nil ||
			s.actors.Despawn(event) != nil {
			s.ack(p, m, false, "invalid_actor_despawn")
			return
		}
		s.ack(p, m, true, "")
		log.Printf("actor despawn id=%s generation=%d", event.ID, event.Generation)
		if s.reconciledActors != nil {
			delete(s.reconciledActors, event.ID)
		}
		_ = s.emit(s.controller, "actor.despawn", m.Session, m.Revision, event)
		_ = s.emit(s.park, "actor.despawn", m.Session, m.Revision, event)
		if s.spawns != nil {
			if id, index, found := s.spawns.FindActor(event.ID); found {
				if status, ok := s.spawns.Lookup(id); ok && status.Units[index].State != "ready" {
					if s.spawns.Fail(id, index, "died_before_ready") == nil {
						s.saveSpawns()
						updated, _ := s.spawns.Lookup(id)
						s.spawnStatus(updated)
						s.pumpSpawns()
					}
				}
			}
		}
	case "world.hello":
		var hello struct {
			MapWidth  int `json:"map_width"`
			MapHeight int `json:"map_height"`
		}
		if m.Decode(&hello) == nil && hello.MapWidth > 0 && hello.MapHeight > 0 && hello.MapWidth <= 1024 && hello.MapHeight <= 1024 {
			s.bwWidth = hello.MapWidth
			s.bwHeight = hello.MapHeight
		}
		s.ack(p, m, true, "")
		s.forwardSnapshot()
		s.sendNavigationMask(s.bw, 0)
		s.sendControllerNavigation(s.controller)
	case "navigation.mask.applied":
		var applied struct {
			Hash     string `json:"hash"`
			Accepted bool   `json:"accepted"`
			Error    string `json:"error"`
		}
		if m.Decode(&applied) != nil || m.Session != s.registry.Session ||
			m.Revision != s.navigationRevision || applied.Hash != s.navigationMask.Hash || !applied.Accepted {
			s.ready = false
			log.Printf("publisher navigation mismatch: hash=%s expected=%s error=%s", applied.Hash, s.navigationMask.Hash, applied.Error)
			_ = s.emit(s.park, "world.error", s.registry.Session, s.registry.Revision,
				map[string]string{"reason": "publisher_navigation_mismatch"})
			return
		}
		s.publisherNavigationReady = true
		log.Printf("publisher navigation hash=%s", applied.Hash)
		s.publishReady()
	case "world.ack":
		var a world.Ack
		_ = m.Decode(&a)
		if execute, found := s.spawnOps[a.OpID]; found {
			delete(s.spawnOps, a.OpID)
			if !a.Accepted && s.spawns != nil {
				if err := s.spawns.Fail(execute.RequestID, execute.Index, a.Error); err == nil {
					s.saveSpawns()
					status, _ := s.spawns.Lookup(execute.RequestID)
					s.spawnStatus(status)
					s.pumpSpawns()
				}
			}
			return
		}
		if strings.HasPrefix(a.OpID, "spawn:") {
			return
		}
		if !a.Accepted && !s.bwResyncPending {
			log.Printf("OpenBW rejected %s: %s", a.OpID, a.Error)
			s.ready = false
			s.bwResyncPending = true
			_ = s.emit(s.park, "world.resync", s.registry.Session, s.registry.Revision, map[string]string{"reason": a.Error})
		}
	case "world.ready":
		if m.Session != s.registry.Session || m.Revision != s.registry.Revision {
			s.ack(p, m, false, "stale_world")
			return
		}
		var ready world.Ready
		if m.Decode(&ready) != nil {
			s.ack(p, m, false, "invalid_ready")
			return
		}
		if ready.Reconciled != nil && !*ready.Reconciled {
			s.ready = false
			s.ack(p, m, true, "")
			_ = s.emit(s.park, "world.resync", m.Session, m.Revision, map[string]string{"reason": "openbw_reconciliation_incomplete"})
			return
		}
		s.ack(p, m, true, "")
		s.pendingReady = &ready
		copyReady := ready
		s.lastReady = &copyReady
		s.publishReady()
	case "combat.event":
		var event world.CombatEvent
		if m.Decode(&event) != nil || event.Type != "destruction" || m.Session != s.registry.Session || !s.ready {
			s.ack(p, m, false, "invalid_combat_event")
			return
		}
		e, ok := s.registry.Entities[event.EntityID]
		if !ok || !e.Destructible || !e.Combat.Targetable || s.registry.Destroyed[e.ID] || event.Health != 0 || s.proxies[e.ID] != event.ProxyID {
			s.ack(p, m, false, "unmapped_target")
			return
		}
		if prior, exists := s.pending[event.ID]; exists {
			s.ack(p, m, prior.EntityID == event.EntityID, "")
			return
		}
		s.pending[event.ID] = event
		if s.pendingFrames == nil {
			s.pendingFrames = map[string]int{}
		}
		s.pendingFrames[event.ID] = m.BWTick
		s.registry.RemovalState[event.EntityID] = "destruction_requested"
		s.ack(p, m, true, "")
		if err := s.emit(s.park, "combat.event", m.Session, s.registry.Revision, event); err == nil {
			s.registry.RemovalState[event.EntityID] = "removal_pending"
		}
	case "entity.state":
		var payload targetLink
		if m.Decode(&payload) != nil || m.Session != s.registry.Session || m.Revision != s.registry.Revision ||
			s.registry.Entities[payload.ID].ID == "" || payload.ProxyID == "" ||
			payload.X < 0 || payload.Y < 0 || payload.X >= s.bwWidth*32 || payload.Y >= s.bwHeight*32 {
			s.ack(p, m, false, "unknown_entity")
			return
		}
		if previous := s.proxies[payload.ID]; previous != "" && previous != payload.ProxyID {
			s.ack(p, m, false, "proxy_identity_changed")
			return
		}
		s.proxies[payload.ID] = payload.ProxyID
		if s.targetLinks == nil {
			s.targetLinks = map[string]targetLink{}
		}
		s.targetLinks[payload.ID] = payload
		s.ack(p, m, true, "")
		s.sendTargetLink(s.controller, m.Session, m.Revision, payload)
	case "combat.snapshot":
		if m.Session == s.registry.Session && s.ready && len(m.Payload) <= 131072 {
			var snapshot struct {
				Seq         uint64           `json:"seq"`
				BWTick      int              `json:"bw_tick"`
				UnitTotal   int              `json:"unit_total"`
				UnitOmitted int              `json:"unit_omitted"`
				Units       []map[string]any `json:"units"`
			}
			if m.Decode(&snapshot) == nil {
				s.nativeOccupancyComplete = false
				if s.scenario != nil && snapshot.UnitOmitted == 0 && snapshot.UnitTotal <= len(snapshot.Units) {
					marines, zerglings := 0, 0
					occupants := make([]world.NativeOccupant, 0, snapshot.UnitTotal)
					living := map[string]bool{}
					for _, unit := range snapshot.Units {
						if unit["alive"] != true {
							continue
						}
						if id, ok := unit["id"].(string); ok {
							living[id] = true
						}
						if x, ok := unit["x"].(float64); ok {
							if y, ok := unit["y"].(float64); ok {
								occupants = append(occupants, world.NativeOccupant{X: int(x), Y: int(y)})
							}
						}
						switch unit["kind"] {
						case "terran_marine":
							marines++
						case "zerg_zergling":
							zerglings++
						}
					}
					s.lastMarines, s.lastZerglings = marines, zerglings
					s.nativeOccupants, s.nativeOccupancyComplete = occupants, true
					if s.runtime != nil {
						s.advanceScenarioRuntime(snapshot.BWTick, snapshot.Seq, living)
					}
					s.announceOutcome(marines, zerglings)
					s.publishScenarioStatus(false)
				}
				visible := make([]map[string]any, 0, len(snapshot.Units))
				for _, unit := range snapshot.Units {
					x, xOK := unit["x"].(float64)
					y, yOK := unit["y"].(float64)
					if !xOK || !yOK {
						snapshot.UnitOmitted++
						continue
					}
					parkX, parkY := s.transform.InverseX(int(x)), s.transform.InverseY(int(y))
					if parkX < 0 || parkY < 0 || parkX >= s.registry.Width*32 ||
						parkY >= s.registry.Height*32 {
						snapshot.UnitOmitted++
						continue
					}
					unit["x"], unit["y"] = parkX, parkY
					visible = append(visible, unit)
				}
				snapshot.Units = visible
				_ = s.emit(s.park, "combat.snapshot", m.Session, s.registry.Revision, snapshot)
			}
		}
	default:
		s.ack(p, m, false, "unsupported_operation")
	}
}
func (s *service) controllerMessage(p *peer, m world.Envelope) {
	if m.Source != "openbw" {
		s.ack(p, m, false, "wrong_authority")
		return
	}
	switch m.Kind {
	case "world.hello":
		s.ack(p, m, true, "")
		if s.registry.Session != "" {
			_ = s.emit(p, "world.hello", s.registry.Session, s.registry.Revision,
				map[string]any{"role": "controller"})
			s.controllerNavigationReady = false
			s.sendControllerNavigation(p)
			s.sendTargetLinks(p)
			if s.actors != nil {
				for _, identity := range s.actors.Living() {
					_ = s.emit(p, "actor.spawn", s.registry.Session, s.registry.Revision, identity)
					if record, ok := s.actors.Lookup(identity.ID); ok {
						if binding, found := record.Bindings["publisher"]; found {
							_ = s.emit(p, "actor.bind", s.registry.Session, s.registry.Revision, binding)
						}
					}
				}
			}
			s.publishReady()
		}
	case "navigation.mask.applied":
		var applied struct {
			Hash     string `json:"hash"`
			Accepted bool   `json:"accepted"`
			Error    string `json:"error"`
		}
		if m.Decode(&applied) != nil || m.Session != s.registry.Session ||
			m.Revision != s.navigationRevision || applied.Hash != s.navigationMask.Hash || !applied.Accepted {
			s.ready = false
			log.Printf("controller navigation mismatch: hash=%s expected=%s error=%s", applied.Hash, s.navigationMask.Hash, applied.Error)
			_ = s.emit(s.park, "world.error", s.registry.Session, s.registry.Revision,
				map[string]string{"reason": "controller_navigation_mismatch"})
			return
		}
		s.controllerNavigationReady = true
		log.Printf("controller navigation hash=%s", applied.Hash)
		s.publishReady()
	case "actor.bind":
		var binding world.ActorBinding
		if s.actors == nil || m.Session != s.registry.Session ||
			m.Revision != s.registry.Revision || m.Decode(&binding) != nil ||
			binding.Participant != "controller" || s.actors.Bind(binding) != nil {
			s.ack(p, m, false, "invalid_actor_binding")
			return
		}
		s.ack(p, m, true, "")
		log.Printf("actor binding id=%s participant=controller native=%s active=%t", binding.ID,
			binding.NativeID, s.actors.Commandable(binding.ID))
		if s.actors.Commandable(binding.ID) {
			_ = s.emit(s.park, "actor.bind", m.Session, m.Revision, binding)
			s.spawnActorReady(binding.ID)
		}
	case "world.ack":
		var answer world.Ack
		if m.Decode(&answer) != nil || m.Session != s.registry.Session {
			return
		}
		if _, exists := s.pendingLinks[answer.OpID]; !exists {
			return
		}
		delete(s.pendingLinks, answer.OpID)
		if !answer.Accepted {
			s.ready = false
			s.pendingReady = nil
			_ = s.emit(s.park, "world.resync", m.Session, s.registry.Revision,
				map[string]string{"reason": "controller_target_link_rejected"})
			return
		}
		s.publishReady()
	case "combat.result":
		var result struct {
			CommandID string `json:"command_id"`
			PlayerID  int    `json:"player_id"`
			RequestID int    `json:"request_id"`
			Accepted  bool   `json:"accepted"`
			Reason    string `json:"reason"`
		}
		if m.Decode(&result) != nil || m.Session != s.registry.Session || m.Revision != s.registry.Revision {
			s.ack(p, m, false, "stale_command_result")
			return
		}
		command, found := s.commands[result.CommandID]
		if !found || command.PlayerID != result.PlayerID || command.RequestID != result.RequestID {
			s.ack(p, m, false, "unknown_command")
			return
		}
		delete(s.commands, result.CommandID)
		s.ack(p, m, true, "")
		_ = s.emit(s.park, "combat.result", m.Session, m.Revision, result)
	default:
		s.ack(p, m, false, "unsupported_operation")
	}
}
func (s *service) serve(listener net.Listener, role string) {
	for {
		conn, err := listener.Accept()
		if err != nil {
			log.Print(err)
			return
		}
		p := &peer{Conn: conn}
		s.mu.Lock()
		if role == "park" {
			if s.park != nil {
				_ = s.park.Close()
			}
			s.park = p
			s.stage = nil
		} else if role == "bw" {
			if s.bw != nil {
				_ = s.bw.Close()
			}
			s.bw = p
			s.ready = false
		} else {
			if s.controller != nil {
				_ = s.controller.Close()
			}
			s.controller = p
			s.pendingLinks = map[string]string{}
		}
		s.mu.Unlock()
		log.Printf("%s connected", role)
		go s.consume(role, p)
	}
}
func main() {
	parkAddress := flag.String("park", "127.0.0.1:40010", "OpenRCT2 adapter listener")
	bwAddress := flag.String("openbw", "127.0.0.1:40011", "OpenBW adapter listener")
	controllerAddress := flag.String("controller", "127.0.0.1:40012", "OpenBW player controller listener")
	rulesPath := flag.String("rules", "", "optional JSON mapping overrides")
	scenarioPath := flag.String("scenario", "", "optional first-playable scenario configuration")
	spawnJournal := flag.String("spawn-journal", "run-data/spawn-queue.json", "durable spawn request journal")
	maxLiveActors := flag.Int("max-live-actors", 240, "maximum native Marine and Zergling actors (1-256)")
	flag.Parse()
	if *maxLiveActors < 1 || *maxLiveActors > 256 {
		log.Fatal("max-live-actors must be 1-256")
	}
	var scenario *world.Scenario
	if *scenarioPath != "" {
		var err error
		scenario, err = world.LoadScenario(*scenarioPath)
		if err != nil {
			log.Fatal(err)
		}
	}
	mapping := world.DefaultMapping()
	if *rulesPath != "" {
		data, err := os.ReadFile(*rulesPath)
		if err != nil {
			log.Fatal(err)
		}
		var extra world.Mapping
		if err = json.Unmarshal(data, &extra); err != nil {
			log.Fatal(err)
		}
		mapping.Rules = append(mapping.Rules, extra.Rules...)
	}
	park, err := net.Listen("tcp", *parkAddress)
	if err != nil {
		log.Fatal(err)
	}
	defer park.Close()
	bw, err := net.Listen("tcp", *bwAddress)
	if err != nil {
		log.Fatal(err)
	}
	defer bw.Close()
	controller, err := net.Listen("tcp", *controllerAddress)
	if err != nil {
		log.Fatal(err)
	}
	defer controller.Close()
	s := &service{registry: world.NewRegistry(), mapping: mapping, pending: map[string]world.CombatEvent{}, proxies: map[string]string{}, scenario: scenario,
		spawnJournalPath: *spawnJournal, maxLiveActors: *maxLiveActors}
	log.Printf("world.v1 listening park=%s openbw=%s controller=%s", *parkAddress, *bwAddress, *controllerAddress)
	go s.serve(bw, "bw")
	go s.serve(controller, "controller")
	s.serve(park, "park")
}
