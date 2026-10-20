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
	if perf.file == nil {
		return json.NewEncoder(p.Conn).Encode(m)
	}
	started := monoNS()
	encoded, err := json.Marshal(m)
	if err != nil {
		return err
	}
	encoded = append(encoded, '\n')
	encodedNS := monoNS()
	written := 0
	for written < len(encoded) {
		n, writeErr := p.Conn.Write(encoded[written:])
		written += n
		if writeErr != nil {
			err = writeErr
			break
		}
		if n == 0 {
			err = fmt.Errorf("short socket write")
			break
		}
	}
	perf.event("socket_write", map[string]any{"kind": m.Kind, "session": m.Session,
		"bytes": len(encoded), "written": written, "encode_us": (encodedNS - started) / 1000,
		"write_us": (monoNS() - encodedNS) / 1000})
	return err
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
	targetPatch               *targetPatchStage
	next                      uint64
	pending                   map[string]world.CombatEvent
	pendingFrames             map[string]int
	proxies                   map[string]string
	targetLinks               map[string]targetLink
	pendingLinks              map[string]pendingTargetLink
	deferredLinks             map[string]bool
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
	lastEnemies               int
	lastNativeActors          int
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
	parkSupervisorSocket      string
	parkGeneration            string
}

type parkPatchStage struct {
	patch                                   world.Patch
	combatResult                            *world.CombatResult
	digest                                  string
	candidate                               *world.Registry
	mask                                    world.NavigationMask
	created                                 time.Time
	maskChanged                             bool
	publisherStaged, controllerStaged       bool
	publisherScheduled, controllerScheduled bool
	publisherApplied, controllerApplied     bool
	publisherFrame, controllerFrame         int
	applyFrame                              int
}

type targetPatchStage struct {
	id               string
	hash             string
	frame            int
	created          time.Time
	targetStarted    time.Time
	objectiveRemoved bool
}

type worldCommand struct {
	CommandID     string   `json:"command_id"`
	PlayerID      int      `json:"player_id"`
	RequestID     int      `json:"request_id"`
	UnitIDs       []string `json:"unit_ids"`
	Verb          string   `json:"verb"`
	UnitType      string   `json:"unit_type,omitempty"`
	TargetID      string   `json:"target_id,omitempty"`
	TargetProxyID string   `json:"target_proxy_id,omitempty"`
	X             int      `json:"x,omitempty"`
	Y             int      `json:"y,omitempty"`
}

func supportedNativeBuilding(id string) bool {
	_, ok := world.SupportedBuilding(id)
	return ok
}

func (s *service) mayOrderProduction(owner int) bool {
	if owner == 1 {
		return true
	}
	if s.scenario != nil {
		for _, allowed := range s.scenario.ProductionControlOwners {
			if allowed == owner {
				return true
			}
		}
	}
	return false
}

type targetLink struct {
	ID      string `json:"id"`
	ProxyID string `json:"proxy_id"`
	X       int    `json:"proxy_x"`
	Y       int    `json:"proxy_y"`
	Health  int    `json:"health"`
}

type pendingTargetLink struct {
	ID       string
	Revision uint64
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
	traceDir := os.Getenv("BRIDGE_NAV_DIAGNOSTICS_DIR")
	var mask world.NavigationMask
	var err error
	if traceDir != "" {
		mask, err = world.DeriveNavigationTrace(s.registry, s.transform, s.bwWidth, s.bwHeight)
	} else {
		mask, err = world.DeriveNavigation(s.registry, s.transform, s.bwWidth, s.bwHeight)
	}
	if err != nil {
		return err
	}
	if traceDir != "" {
		writeNavigationDiagnostic(traceDir, "confirmed", s.registry, mask)
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

func writeNavigationDiagnostic(dir, state string, registry *world.Registry, mask world.NavigationMask) {
	if dir == "" || registry == nil {
		return
	}
	entities := make([]world.Entity, 0, len(registry.Entities))
	for _, id := range registry.IDs() {
		entities = append(entities, registry.Entities[id])
	}
	data := map[string]any{"state": state, "revision": registry.Revision,
		"park_width": registry.Width, "park_height": registry.Height,
		"native_width": mask.Width, "native_height": mask.Height,
		"hash": mask.Hash, "mask_hex": hex.EncodeToString(mask.Bits),
		"terrain": registry.Terrain, "entities": entities, "causes": mask.Causes}
	encoded, err := json.MarshalIndent(data, "", "  ")
	if err != nil {
		log.Printf("navigation diagnostic encoding failed: %v", err)
		return
	}
	if err := os.MkdirAll(dir, 0755); err != nil {
		log.Printf("navigation diagnostic directory failed: %v", err)
		return
	}
	name := fmt.Sprintf("%s-revision-%d.json", state, registry.Revision)
	if err := os.WriteFile(dir+"/"+name, encoded, 0644); err != nil {
		log.Printf("navigation diagnostic write failed: %v", err)
	}
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
	s.sendMask(p, s.navigationMask, s.registry.Revision, applyFrame, false)
}

func (s *service) sendMask(p *peer, mask world.NavigationMask, revision uint64, applyFrame int, stageOnly bool) {
	const bytesPerChunk = 6000
	chunks := (len(mask.Bits) + bytesPerChunk - 1) / bytesPerChunk
	log.Printf("native navigation transfer bytes=%d hex_bytes=%d chunks=%d stage_only=%t",
		len(mask.Bits), len(mask.Bits)*2, chunks, stageOnly)
	if err := s.emit(p, "navigation.mask.begin", s.registry.Session, revision,
		map[string]any{"width": s.bwWidth, "height": s.bwHeight, "chunks": chunks,
			"hash": mask.Hash, "apply_frame": applyFrame, "stage_only": stageOnly}); err != nil {
		log.Printf("navigation begin: %v", err)
		return
	}
	for index, start := 0, 0; start < len(mask.Bits); index, start = index+1, start+bytesPerChunk {
		end := start + bytesPerChunk
		if end > len(mask.Bits) {
			end = len(mask.Bits)
		}
		if err := s.emit(p, "navigation.mask.chunk", s.registry.Session, revision,
			map[string]any{"index": index, "hex": hex.EncodeToString(mask.Bits[start:end])}); err != nil {
			log.Printf("navigation chunk: %v", err)
			return
		}
	}
	if err := s.emit(p, "navigation.mask.end", s.registry.Session, revision,
		map[string]string{"hash": mask.Hash}); err != nil {
		log.Printf("navigation end: %v", err)
	}
}

func (s *service) startNativePatch() {
	patch := s.parkPatch
	if patch == nil {
		return
	}
	for _, participant := range []*peer{s.bw, s.controller} {
		if patch.maskChanged {
			s.sendMask(participant, patch.mask, patch.patch.ResultRevision, 0, true)
		} else {
			_ = s.emit(participant, "navigation.revision.stage", s.registry.Session,
				patch.patch.ResultRevision, map[string]string{"hash": patch.mask.Hash})
		}
	}
}

func (s *service) failNativePatch(reason string) {
	if s.parkPatch == nil {
		return
	}
	patch := s.parkPatch
	s.cancelNativePatch(patch)
	s.parkPatch = nil
	s.ready = false
	log.Printf("park patch unsynchronized id=%s revision=%d reason=%s", patch.patch.ID,
		patch.patch.ResultRevision, reason)
	_ = s.emit(s.park, "world.patch.status", s.registry.Session, patch.patch.ResultRevision,
		map[string]any{"patch_id": patch.patch.ID, "state": "unsynchronized", "reason": reason,
			"navigation_hash": patch.mask.Hash, "apply_frame": patch.applyFrame})
}

func (s *service) cancelNativePatch(patch *parkPatchStage) {
	if patch == nil {
		return
	}
	for _, participant := range []*peer{s.bw, s.controller} {
		_ = s.emit(participant, "navigation.mask.cancel", s.registry.Session,
			patch.patch.ResultRevision, map[string]string{"hash": patch.mask.Hash})
	}
}

func (s *service) nativePatchReport(participant string, m world.Envelope) bool {
	if m.Kind != "navigation.mask.staged" && m.Kind != "navigation.mask.scheduled" &&
		m.Kind != "navigation.mask.applied" {
		return false
	}
	patch := s.parkPatch
	if patch == nil || m.Session != s.registry.Session || m.Revision != patch.patch.ResultRevision {
		return m.Kind != "navigation.mask.applied"
	}
	var report struct {
		Hash       string `json:"hash"`
		Accepted   bool   `json:"accepted"`
		Error      string `json:"error"`
		ApplyFrame int    `json:"apply_frame"`
	}
	if m.Decode(&report) != nil || !report.Accepted || report.Hash != patch.mask.Hash {
		s.failNativePatch(participant + ":" + report.Error)
		return true
	}
	switch m.Kind {
	case "navigation.mask.staged":
		if participant == "publisher" {
			patch.publisherStaged, patch.publisherFrame = true, m.BWTick
		} else {
			patch.controllerStaged, patch.controllerFrame = true, m.BWTick
		}
		if patch.publisherStaged && patch.controllerStaged && patch.applyFrame == 0 {
			frame := patch.publisherFrame
			if patch.controllerFrame > frame {
				frame = patch.controllerFrame
			}
			lead := int(time.Since(patch.created).Milliseconds()/42)*2 + 32
			if lead < 96 {
				lead = 96
			}
			patch.applyFrame = frame + lead
			for _, peer := range []*peer{s.bw, s.controller} {
				_ = s.emit(peer, "navigation.mask.schedule", s.registry.Session,
					patch.patch.ResultRevision, map[string]any{"hash": patch.mask.Hash,
						"apply_frame": patch.applyFrame})
			}
			log.Printf("park patch scheduled id=%s hash=%s frame=%d lead=%d",
				patch.patch.ID, patch.mask.Hash, patch.applyFrame, lead)
		}
	case "navigation.mask.scheduled":
		if report.ApplyFrame != patch.applyFrame || patch.applyFrame == 0 {
			s.failNativePatch("native_schedule_frame_mismatch")
			return true
		}
		if participant == "publisher" {
			patch.publisherScheduled = true
		} else {
			patch.controllerScheduled = true
		}
		if patch.publisherScheduled && patch.controllerScheduled {
			_ = s.emit(s.park, "world.patch.status", s.registry.Session, patch.patch.ResultRevision,
				map[string]any{"patch_id": patch.patch.ID, "state": "scheduled",
					"navigation_hash": patch.mask.Hash, "apply_frame": patch.applyFrame})
		}
	case "navigation.mask.applied":
		if !patch.publisherScheduled || !patch.controllerScheduled || m.BWTick != patch.applyFrame {
			s.failNativePatch("native_application_frame_mismatch")
			return true
		}
		if participant == "publisher" {
			patch.publisherApplied = true
		} else {
			patch.controllerApplied = true
		}
		if patch.publisherApplied && patch.controllerApplied {
			if err := s.registry.CommitPatch(patch.patch, patch.candidate); err != nil {
				s.failNativePatch(err.Error())
				return true
			}
			s.navigationMask, s.navigationRevision = patch.mask, patch.patch.ResultRevision
			s.publisherNavigationReady, s.controllerNavigationReady, s.ready = true, true, true
			s.parkPatch = nil
			if patch.combatResult != nil {
				result := *patch.combatResult
				s.registry.Destroyed[result.EntityID] = true
				s.registry.RemovalState[result.EntityID] = result.State
				if s.runtime != nil && result.EntityID == s.objectiveID {
					s.runtime.ObjectiveDestroyed = true
					if !s.saveScenarioRuntime() {
						s.scenarioRuntimeError(fmt.Errorf("scenario_journal_unavailable"))
						return true
					}
				}
				delete(s.targetLinks, result.EntityID)
				delete(s.proxies, result.EntityID)
				delete(s.pending, result.EventID)
				delete(s.pendingFrames, result.EventID)
				_ = s.emit(s.controller, "entity.remove", s.registry.Session, s.registry.Revision,
					map[string]string{"id": result.EntityID})
				_ = s.emit(s.park, "entity.remove", s.registry.Session, s.registry.Revision,
					map[string]string{"id": result.EntityID})
				_ = s.emit(s.park, "world.patch.status", s.registry.Session, s.registry.Revision,
					map[string]any{"patch_id": patch.patch.ID, "state": "synchronized",
						"navigation_hash": patch.mask.Hash, "apply_frame": patch.applyFrame})
				log.Printf("combat demolition synchronized id=%s revision=%d hash=%s frame=%d",
					result.EntityID, s.registry.Revision, patch.mask.Hash, patch.applyFrame)
				if result.EntityID == s.objectiveID {
					s.announceOutcome(s.lastMarines, s.lastEnemies)
				}
				s.publishReady()
				s.pumpSpawns()
				return true
			}
			if err := s.syncPatchTargets(patch.patch); err != nil {
				s.ready = false
				_ = s.emit(s.park, "world.patch.status", s.registry.Session, s.registry.Revision,
					map[string]any{"patch_id": patch.patch.ID, "state": "unsynchronized",
						"reason": "target_reconciliation_unavailable", "navigation_hash": patch.mask.Hash})
				log.Printf("park patch target reconciliation failed id=%s: %v", patch.patch.ID, err)
				return true
			}
			objectiveRemoved := false
			for _, id := range patch.patch.Removals {
				if id == s.objectiveID {
					objectiveRemoved = true
				}
			}
			s.targetPatch = &targetPatchStage{id: patch.patch.ID, hash: patch.mask.Hash,
				frame: patch.applyFrame, created: patch.created, targetStarted: time.Now(),
				objectiveRemoved: objectiveRemoved}
			log.Printf("park patch navigation applied id=%s revision=%d hash=%s frame=%d",
				patch.patch.ID, s.registry.Revision, patch.mask.Hash, patch.applyFrame)
		}
	}
	return true
}

func (s *service) syncPatchTargets(patch world.Patch) error {
	removed := append([]string(nil), patch.Removals...)
	for _, changed := range patch.Modifications {
		entity := s.registry.Entities[changed.ID]
		if !entity.Destructible || !entity.Combat.Targetable {
			removed = append(removed, entity.ID)
		}
	}
	for _, id := range removed {
		delete(s.proxies, id)
		delete(s.targetLinks, id)
		_ = s.emit(s.controller, "entity.remove", s.registry.Session, s.registry.Revision,
			map[string]string{"id": id})
		_ = s.emit(s.park, "entity.remove", s.registry.Session, s.registry.Revision,
			map[string]string{"id": id})
	}
	additions := make([]world.Entity, 0, len(patch.Additions))
	modifications := make([]world.Entity, 0, len(patch.Modifications))
	for _, entity := range patch.Additions {
		additions = append(additions, s.transform.Entity(s.registry.Entities[entity.ID]))
	}
	for _, entity := range patch.Modifications {
		modifications = append(modifications, s.transform.Entity(s.registry.Entities[entity.ID]))
	}
	payload := map[string]any{"patch_id": patch.ID, "additions": additions,
		"modifications": modifications, "removals": patch.Removals}
	encoded, err := json.Marshal(payload)
	if err != nil {
		return err
	}
	if len(encoded) > 900000 {
		return fmt.Errorf("target_patch_transport_limit: %d bytes", len(encoded))
	}
	return s.emit(s.bw, "world.patch.targets", s.registry.Session, s.registry.Revision, payload)
}

func (s *service) sendTargetLink(p *peer, session string, revision uint64, link targetLink) {
	if p == nil {
		return
	}
	opID := s.operation()
	if p.send(world.Message("entity.state", session, opID, "bridge", revision, link)) == nil {
		if s.pendingLinks == nil {
			s.pendingLinks = map[string]pendingTargetLink{}
		}
		s.pendingLinks[opID] = pendingTargetLink{ID: link.ID, Revision: revision}
	}
}

func (s *service) publishReady() {
	if s.controller != nil && s.parkPatch == nil && s.targetPatch == nil && len(s.deferredLinks) > 0 {
		for id := range s.deferredLinks {
			if link, ok := s.targetLinks[id]; ok && !s.registry.Destroyed[id] {
				s.sendTargetLink(s.controller, s.registry.Session, s.registry.Revision, link)
			}
		}
		s.deferredLinks = nil
	}
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
		destroyed := s.runtime != nil && (s.runtime.ObjectiveDestroyed || s.runtime.ObjectiveRemoved) && s.runtime.Outcome == "defeat"
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
	if len(s.pending) != 0 {
		ids := make([]string, 0, len(s.pending))
		for id := range s.pending {
			ids = append(ids, id)
		}
		sort.Strings(ids)
		for _, id := range ids {
			event := s.pending[id]
			if s.emit(s.park, "combat.event", s.registry.Session, s.registry.Revision, event) == nil {
				s.registry.RemovalState[event.EntityID] = "removal_pending"
				log.Printf("replayed combat demolition id=%s entity=%s", id, event.EntityID)
			}
		}
	}
	s.publishScenarioStatus(true)
	log.Printf("OpenBW ready targets=%d unsupported=%d", ready.Targets, ready.UnsupportedTotal)
	if s.scenario == nil || s.scenario.Version == 1 {
		s.submitScenarioSpawns()
	}
	s.reconcileUncertainSpawn()
	s.pumpSpawns()
}

func (s *service) announceOutcome(marines, enemies int) {
	if s.scenario == nil || s.outcome != "" || s.objectiveID == "" || !s.ready {
		return
	}
	removed := s.runtime != nil && s.runtime.ObjectiveRemoved
	state := s.scenario.Outcome(s.registry.Destroyed[s.objectiveID] || removed, marines, enemies)
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
	outcome := map[string]any{"scenario_id": s.scenario.ID, "state": state,
		"objective_id": s.objectiveID, "marines": marines, "zerglings": s.lastZerglings, "enemies": enemies}
	if removed {
		outcome["reason"] = "objective_removed_manually"
	}
	_ = s.emit(s.park, "world.outcome", s.registry.Session, s.registry.Revision, outcome)
	log.Printf("scenario %s outcome=%s marines=%d enemies=%d", s.scenario.ID, state, marines, enemies)
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
		readNS := monoNS()
		var m world.Envelope
		if err := json.Unmarshal(scanner.Bytes(), &m); err != nil {
			log.Printf("%s malformed JSON: %v", role, err)
			continue
		}
		if perf.file != nil && (m.Kind == "combat.snapshot" || m.Kind == "combat.command" || m.Kind == "combat.result") {
			perf.event("message_read", map[string]any{"kind": m.Kind, "role": role, "session": m.Session,
				"bytes": len(scanner.Bytes()), "decode_us": (monoNS() - readNS) / 1000,
				"queue_wait_us": 0})
		}
		if err := m.Validate(); err != nil {
			log.Printf("%s invalid %s: %v", role, m.Kind, err)
			s.mu.Lock()
			s.ack(p, m, false, err.Error())
			s.mu.Unlock()
			continue
		}
		queueNS := monoNS()
		s.mu.Lock()
		if (role == "park" && s.park == p) || (role == "bw" && s.bw == p) ||
			(role == "controller" && s.controller == p) {
			handleNS := monoNS()
			s.handle(role, p, m)
			if perf.file != nil && (m.Kind == "combat.snapshot" || m.Kind == "combat.command" || m.Kind == "combat.result") {
				perf.event("message_handle", map[string]any{"kind": m.Kind, "role": role, "session": m.Session,
					"queue_us": (handleNS - queueNS) / 1000, "process_us": (monoNS() - handleNS) / 1000})
			}
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
		s.failNativePatch("publisher_disconnected")
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
		s.failNativePatch("controller_disconnected")
		if s.actors != nil {
			s.actors.UnbindParticipant("controller")
		}
		s.controllerNavigationReady = false
		s.ready = false
		if s.lastReady != nil {
			copyReady := *s.lastReady
			s.pendingReady = &copyReady
		}
		s.pendingLinks = map[string]pendingTargetLink{}
		s.deferredLinks = nil
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
		s.cancelNativePatch(s.parkPatch)
		s.stage = &staging{session: m.Session, revision: m.Revision, begin: b, seen: map[string]bool{}}
		s.parkPatch = nil
		s.targetPatch = nil
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
		pendingCombat, pendingCombatFrames := s.pending, s.pendingFrames
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
		if previousSession == m.Session {
			for id, event := range pendingCombat {
				if s.registry.Entities[event.EntityID].ID != "" && !s.registry.Destroyed[event.EntityID] {
					s.pending[id] = event
					s.pendingFrames[id] = pendingCombatFrames[id]
				}
			}
		}
		if previousSession != m.Session {
			s.proxies = map[string]string{}
			s.targetLinks = map[string]targetLink{}
		} else {
			for id := range s.proxies {
				if s.registry.Entities[id].ID == "" || s.registry.Destroyed[id] {
					delete(s.proxies, id)
					delete(s.targetLinks, id)
					_ = s.emit(s.controller, "entity.remove", m.Session, m.Revision,
						map[string]string{"id": id})
				}
			}
			log.Printf("same-session park reconciliation revision=%d continuing_targets=%d",
				m.Revision, len(s.proxies))
		}
		s.pendingLinks = map[string]pendingTargetLink{}
		s.deferredLinks = nil
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
			s.lastEnemies = 0
			s.lastNativeActors = 0
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
		if s.targetPatch != nil {
			s.ack(p, m, false, "target_reconciliation_in_progress")
			return
		}
		if s.parkPatch != nil {
			if time.Since(s.parkPatch.created) > 30*time.Second {
				log.Printf("park patch expired id=%s", s.parkPatch.patch.ID)
				s.cancelNativePatch(s.parkPatch)
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
		if !s.ready || s.bw == nil || s.controller == nil {
			s.ack(p, m, false, "native_participant_unavailable")
			return
		}
		if s.bwWidth == 0 || s.bwHeight == 0 {
			s.ack(p, m, false, "native_dimensions_unavailable")
			return
		}
		validationStarted := time.Now()
		candidate, mask, err := s.registry.StagePatch(m.Session, patch, s.mapping,
			s.transform, s.bwWidth, s.bwHeight)
		log.Printf("park patch validated id=%s elapsed_ms=%d navigation_us=%d accepted=%t", patch.ID,
			time.Since(validationStarted).Milliseconds(), mask.DerivationTime.Microseconds(), err == nil)
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
		if traceDir := os.Getenv("BRIDGE_NAV_DIAGNOSTICS_DIR"); traceDir != "" {
			traced, traceErr := world.DeriveNavigationTrace(candidate, s.transform, s.bwWidth, s.bwHeight)
			if traceErr == nil && traced.Hash == mask.Hash {
				writeNavigationDiagnostic(traceDir, "candidate", candidate, traced)
			} else {
				log.Printf("navigation diagnostic mismatch: %v", traceErr)
			}
		}
		if s.navigationMask.Hash == "" {
			confirmed, err := world.DeriveNavigation(s.registry, s.transform, s.bwWidth, s.bwHeight)
			if err != nil {
				s.ack(p, m, false, err.Error())
				return
			}
			s.navigationMask = confirmed
			s.navigationRevision = s.registry.Revision
		}
		s.parkPatch = &parkPatchStage{patch: patch, digest: patch.Digest(),
			candidate: candidate, mask: mask, created: time.Now(),
			maskChanged: mask.Hash != s.navigationMask.Hash}
		s.ready = false
		s.ack(p, m, true, "")
		_ = s.emit(p, "world.patch.status", m.Session, m.Revision,
			map[string]any{"patch_id": patch.ID, "state": "staged", "navigation_hash": mask.Hash})
		log.Printf("park patch staged id=%s base=%d result=%d hash=%s", patch.ID,
			patch.BaseRevision, patch.ResultRevision, mask.Hash)
		s.startNativePatch()
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
				s.cancelNativePatch(s.parkPatch)
				s.parkPatch = nil
				s.ready = false
			} else {
				state, reason, hash = "staged", "", s.parkPatch.mask.Hash
			}
		} else if s.targetPatch != nil && s.targetPatch.id == query.PatchID {
			if time.Since(s.targetPatch.created) > 30*time.Second {
				state, reason, hash = "unsynchronized", "target_reconciliation_expired", s.targetPatch.hash
				s.targetPatch = nil
				s.ready = false
			} else {
				state, reason, hash = "scheduled", "native_targets_pending", s.targetPatch.hash
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
		if s.parkPatch != nil || s.targetPatch != nil {
			s.ready = false
			s.ack(p, m, false, "patch_in_progress")
			_ = s.emit(p, "world.resync", s.registry.Session, s.registry.Revision,
				map[string]string{"reason": "patch_in_progress"})
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
			patch := world.Patch{ID: "combat:" + result.EventID, BaseRevision: s.registry.Revision,
				ResultRevision: m.Revision, Removals: []string{result.EntityID},
				Counts: world.PatchCounts{Removals: 1}}
			candidate, mask, err := s.registry.StagePatch(m.Session, patch, s.mapping,
				s.transform, s.bwWidth, s.bwHeight)
			if err != nil {
				s.ack(p, m, false, err.Error())
				return
			}
			candidate.Destroyed[result.EntityID] = true
			candidate.RemovalState[result.EntityID] = result.State
			s.parkPatch = &parkPatchStage{patch: patch, digest: patch.Digest(),
				candidate: candidate, mask: mask, created: time.Now(),
				maskChanged: mask.Hash != s.navigationMask.Hash, combatResult: &result}
			s.ready = false
			s.ack(p, m, true, "")
			_ = s.emit(p, "world.patch.status", m.Session, m.Revision,
				map[string]any{"patch_id": patch.ID, "state": "staged", "navigation_hash": mask.Hash})
			// Retire the dead proxy immediately so it cannot keep occupying the
			// demolished footprint while navigation waits for its common frame.
			// The base revision keeps native navigation staging ordered.
			_ = s.emit(s.bw, "combat.result", m.Session, s.registry.Revision, result)
			s.startNativePatch()
			return
		}
		s.registry.RemovalState[result.EntityID] = result.State
		delete(s.pending, result.EventID)
		s.ack(p, m, true, "")
		_ = s.emit(s.bw, "combat.result", m.Session, s.registry.Revision, result)
		s.ready = false
		_ = s.emit(s.park, "world.resync", m.Session, s.registry.Revision, map[string]string{"reason": "removal_failed"})
		delete(s.pendingFrames, result.EventID)
	case "entity.upsert", "entity.remove", "entity.transform", "entity.state", "navigation.terrain.update":
		// The envelope and model are versioned for future live updates. Applying
		// one side before OpenBW accepts its geometry would split authority.
		s.ack(p, m, false, "live_update_unsupported")
	case "unit.spawn.request", "unit.spawn.query", "unit.spawn.cancel":
		if m.Kind == "unit.spawn.request" && s.scenario != nil && s.scenario.Mode == "park_defense" &&
			s.scenario.ParkDefense.ManualActivation && os.Getenv("BRIDGE_ALLOW_DIRECT_SPAWN") != "1" {
			s.ack(p, m, false, "direct_marine_spawn_disabled")
			return
		}
		s.parkSpawnMessage(p, m)
	case "park.catalog.request":
		s.parkCatalogRequest(p, m)
	case "park.load.request":
		s.parkLoad(p, m)
	case "scenario.wave.request":
		s.parkWaveRequest(p, m)
	case "scenario.defense.request":
		s.parkDefenseConfig(p, m)
	case "combat.command":
		commandNS := monoNS()
		var command worldCommand
		if m.Decode(&command) != nil || m.Session != s.registry.Session || m.Revision != s.registry.Revision ||
			!s.ready || s.outcome != "" || s.controller == nil || command.CommandID == "" || len(command.CommandID) > 128 ||
			command.PlayerID < 0 || command.RequestID < 1 ||
			len(command.UnitIDs) > 32 || s.commands[command.CommandID].CommandID != "" {
			s.ack(p, m, false, "invalid_or_unavailable_command")
			return
		}
		recipient := s.controller
		for _, id := range command.UnitIDs {
			if !unitIDPattern.MatchString(id) {
				s.ack(p, m, false, "invalid_unit_id")
				return
			}
			if s.actors != nil {
				numeric, _ := strconv.Atoi(id[7:])
				record, known := s.actors.Lookup(id)
				if (numeric >= 3000 || known) && !s.actors.Commandable(id) {
					s.ack(p, m, false, "actor_not_bound")
					return
				}
				if known {
					if !s.actors.CombatCommandable(id) {
						s.ack(p, m, false, "actor_not_commandable")
						return
					}
					unit, supported := world.SupportedUnit(record.Identity.Type)
					allowed := false
					for _, verb := range unit.Commands {
						if verb == command.Verb {
							allowed = true
							break
						}
					}
					if !supported || !allowed {
						s.ack(p, m, false, "unsupported_unit_command")
						return
					}
				}
			}
		}
		switch command.Verb {
		case "unit.train":
			entity, exists := s.registry.Entities[command.TargetID]
			building, supported := world.SupportedBuilding(entity.Type)
			if command.UnitType == "" {
				var request map[string]json.RawMessage
				_ = json.Unmarshal(m.Payload, &request)
				if _, explicit := request["unit_type"]; explicit {
					s.ack(p, m, false, "unsupported_unit_type")
					return
				}
				command.UnitType = "terran_marine"
			} // world.v1 legacy default
			_, supportedUnit := world.SupportedUnit(command.UnitType)
			trainable := false
			for _, id := range building.Production {
				if id == command.UnitType {
					trainable = true
					break
				}
			}
			if len(command.UnitIDs) != 0 || !exists || entity.Kind != "structure" ||
				!supported || !supportedUnit || !trainable || entity.Owner < 0 ||
				!s.mayOrderProduction(entity.Owner) ||
				s.registry.Destroyed[command.TargetID] || s.proxies[command.TargetID] == "" {
				s.ack(p, m, false, "production_unavailable")
				return
			}
			command.TargetProxyID = s.proxies[command.TargetID]
			if entity.Owner == 0 {
				recipient = s.bw
			}
		case "unit.move", "unit.attack_move":
			if len(command.UnitIDs) == 0 {
				s.ack(p, m, false, "missing_units")
				return
			}
			if command.X < 0 || command.Y < 0 || command.X >= s.registry.Width*32 || command.Y >= s.registry.Height*32 {
				s.ack(p, m, false, "invalid_destination")
				return
			}
			command.X = s.transform.X(command.X)
			command.Y = s.transform.Y(command.Y)
		case "unit.attack":
			if len(command.UnitIDs) == 0 {
				s.ack(p, m, false, "missing_units")
				return
			}
			if proxy := s.proxies[command.TargetID]; proxy != "" && !s.registry.Destroyed[command.TargetID] {
				command.TargetProxyID = proxy
			} else if unitIDPattern.MatchString(command.TargetID) {
				command.TargetProxyID = command.TargetID
			} else {
				s.ack(p, m, false, "unknown_target")
				return
			}
		case "unit.heal":
			if len(command.UnitIDs) == 0 || !unitIDPattern.MatchString(command.TargetID) {
				s.ack(p, m, false, "invalid_heal_target")
				return
			}
			numeric, _ := strconv.Atoi(command.TargetID[7:])
			if numeric >= 3000 && (s.actors == nil || !s.actors.Commandable(command.TargetID)) {
				s.ack(p, m, false, "invalid_heal_target")
				return
			}
			command.TargetProxyID = command.TargetID
		case "unit.hold", "unit.stop":
			if len(command.UnitIDs) == 0 {
				s.ack(p, m, false, "missing_units")
				return
			}
		default:
			s.ack(p, m, false, "unsupported_command")
			return
		}
		if s.commands == nil {
			s.commands = map[string]worldCommand{}
		}
		if err := s.emit(recipient, "combat.command", m.Session, m.Revision, command); err != nil {
			s.ack(p, m, false, "controller_disconnected")
			return
		}
		s.commands[command.CommandID] = command
		perf.event("command_forward", map[string]any{"session": m.Session, "command_id": command.CommandID,
			"request_id": command.RequestID, "duration_us": (monoNS() - commandNS) / 1000})
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
		entityJSON, _ := json.Marshal(derived)
		if len(entityJSON) > 900000 {
			log.Printf("OpenBW snapshot rejected: entity_too_large id=%s bytes=%d", id, len(entityJSON))
			_ = s.emit(s.park, "world.error", r.Session, rev,
				map[string]string{"reason": "entity_too_large", "entity_id": id})
			return
		}
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
	snapshotBytes, largestChunk := 0, 0
	for _, chunk := range chunks {
		encoded, _ := json.Marshal(chunk)
		snapshotBytes += len(encoded)
		if len(encoded) > largestChunk {
			largestChunk = len(encoded)
		}
	}
	log.Printf("native snapshot transfer entities=%d terrain=%d chunks=%d payload_bytes=%d max_chunk_bytes=%d",
		len(r.Entities), len(derivedTerrain), len(chunks), snapshotBytes, largestChunk)
	begin := world.SnapshotBegin{Width: derivedWidth, Height: derivedHeight, Chunks: len(chunks)}
	if s.scenario != nil && s.scenario.Mode != "park_defense" {
		if s.runtime != nil && (s.runtime.ObjectiveDestroyed || s.runtime.ObjectiveRemoved) {
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
	if s.scenario != nil {
		begin.ScenarioMode = s.scenario.Mode
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
	if s.nativePatchReport("publisher", m) {
		return
	}
	switch m.Kind {
	case "building.state", "player.resources":
		var report struct {
			Owner int `json:"owner"`
		}
		if m.Decode(&report) != nil || report.Owner != 0 {
			return
		}
		s.controllerMessage(p, m)
	case "combat.result":
		var report struct {
			CommandID string `json:"command_id"`
		}
		if m.Decode(&report) != nil {
			return
		}
		command, ok := s.commands[report.CommandID]
		if !ok || command.Verb != "unit.train" ||
			s.registry.Entities[command.TargetID].Owner != 0 {
			return
		}
		s.controllerMessage(p, m)
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
	case "actor.morph":
		var change world.ActorMorph
		if s.actors == nil || m.Session != s.registry.Session ||
			m.Revision != s.registry.Revision || m.Decode(&change) != nil ||
			s.actors.Morph(change) != nil {
			s.ack(p, m, false, "invalid_actor_morph")
			return
		}
		s.ack(p, m, true, "")
		_ = s.emit(s.controller, "actor.morph", m.Session, m.Revision, change)
		_ = s.emit(s.park, "actor.morph", m.Session, m.Revision, change)
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
	case "world.targets.status":
		var status struct {
			PatchID            string         `json:"patch_id"`
			Targets            int            `json:"targets"`
			UnsupportedTotal   int            `json:"unsupported_total"`
			Unsupported        []string       `json:"unsupported"`
			UnsupportedReasons map[string]int `json:"unsupported_reasons"`
		}
		if m.Decode(&status) != nil || s.targetPatch == nil ||
			status.PatchID != s.targetPatch.id || m.Session != s.registry.Session ||
			m.Revision != s.registry.Revision {
			s.ack(p, m, false, "stale_target_status")
			return
		}
		patch := s.targetPatch
		s.targetPatch = nil
		s.ack(p, m, true, "")
		if patch.objectiveRemoved && s.runtime != nil {
			s.runtime.ObjectiveRemoved = true
			if !s.saveScenarioRuntime() {
				s.scenarioRuntimeError(fmt.Errorf("scenario_journal_unavailable"))
				return
			}
			log.Printf("scenario objective removed manually id=%s revision=%d", s.objectiveID, s.registry.Revision)
		}
		if patch.objectiveRemoved {
			s.announceOutcome(s.lastMarines, s.lastEnemies)
		}
		_ = s.emit(s.park, "world.patch.status", s.registry.Session, s.registry.Revision,
			map[string]any{"patch_id": patch.id, "state": "synchronized",
				"navigation_hash": patch.hash, "apply_frame": patch.frame,
				"unsupported_total":   status.UnsupportedTotal,
				"unsupported_reasons": status.UnsupportedReasons})
		log.Printf("park patch synchronized id=%s revision=%d hash=%s frame=%d targets=%d unsupported=%d elapsed_ms=%d target_ms=%d",
			patch.id, s.registry.Revision, patch.hash, patch.frame, status.Targets,
			status.UnsupportedTotal, time.Since(patch.created).Milliseconds(),
			time.Since(patch.targetStarted).Milliseconds())
		if status.UnsupportedTotal > 0 {
			log.Printf("park patch native target unsupported id=%s reasons=%v objects=%v",
				patch.id, status.UnsupportedReasons, status.Unsupported)
		}
		s.publishReady()
		s.pumpSpawns()
	case "entity.retire":
		var retired struct {
			ID      string `json:"id"`
			ProxyID string `json:"proxy_id"`
			Reason  string `json:"reason"`
		}
		if m.Decode(&retired) != nil || m.Session != s.registry.Session ||
			m.Revision != s.registry.Revision || retired.ID == "" ||
			s.proxies[retired.ID] != retired.ProxyID {
			s.ack(p, m, false, "stale_target_retirement")
			return
		}
		delete(s.proxies, retired.ID)
		delete(s.targetLinks, retired.ID)
		log.Printf("native target retired id=%s proxy=%s reason=%s revision=%d", retired.ID,
			retired.ProxyID, retired.Reason, m.Revision)
		s.ack(p, m, true, "")
		_ = s.emit(s.controller, "entity.remove", m.Session, m.Revision, map[string]string{"id": retired.ID})
		_ = s.emit(s.park, "entity.remove", m.Session, m.Revision, map[string]string{"id": retired.ID})
	case "combat.event":
		var event world.CombatEvent
		if m.Decode(&event) != nil || event.Type != "destruction" || m.Session != s.registry.Session {
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
		previousLink, hadLink := s.targetLinks[payload.ID]
		s.proxies[payload.ID] = payload.ProxyID
		if s.targetLinks == nil {
			s.targetLinks = map[string]targetLink{}
		}
		s.targetLinks[payload.ID] = payload
		s.ack(p, m, true, "")
		// Native navigation applies at a common future frame. During staging,
		// the controller can already be on the next revision while the
		// publisher is still reporting health on the previous one.
		if s.parkPatch == nil && s.targetPatch == nil {
			s.sendTargetLink(s.controller, m.Session, m.Revision, payload)
		} else {
			if s.deferredLinks == nil {
				s.deferredLinks = map[string]bool{}
			}
			s.deferredLinks[payload.ID] = true
		}
		if s.lastReady != nil && (!hadLink || previousLink.ProxyID != payload.ProxyID ||
			previousLink.X != payload.X || previousLink.Y != payload.Y || previousLink.Health != payload.Health) {
			_ = s.emit(s.park, "entity.target", m.Session, m.Revision, payload)
		}
		if !hadLink || previousLink.Health != payload.Health {
			log.Printf("native target state id=%s proxy=%s hp=%d revision=%d", payload.ID,
				payload.ProxyID, payload.Health, m.Revision)
		}
	case "combat.snapshot":
		if m.Session == s.registry.Session && (s.ready || s.parkPatch != nil || s.targetPatch != nil) &&
			len(m.Payload) <= 131072 {
			decodeNS := monoNS()
			var snapshot struct {
				Seq         uint64           `json:"seq"`
				BWTick      int              `json:"bw_tick"`
				UnitTotal   int              `json:"unit_total"`
				UnitOmitted int              `json:"unit_omitted"`
				Units       []map[string]any `json:"units"`
			}
			if m.Decode(&snapshot) == nil {
				decodedNS := monoNS()
				s.nativeOccupancyComplete = false
				if s.scenario != nil && snapshot.UnitOmitted == 0 && snapshot.UnitTotal <= len(snapshot.Units) {
					marines, zerglings, enemies := 0, 0, 0
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
						if kind, ok := unit["kind"].(string); ok && world.SupportedEnemyWaveUnit(kind) {
							enemies++
						}
					}
					s.lastMarines, s.lastZerglings, s.lastEnemies = marines, zerglings, enemies
					s.lastNativeActors = len(living)
					s.nativeOccupants, s.nativeOccupancyComplete = occupants, true
					if s.runtime != nil {
						s.advanceScenarioRuntime(snapshot.BWTick, snapshot.Seq, living)
					}
					s.announceOutcome(marines, enemies)
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
				transformNS := monoNS()
				perf.event("snapshot_transform", map[string]any{"session": m.Session, "seq": snapshot.Seq,
					"bw_tick": snapshot.BWTick, "revision": s.registry.Revision, "unit_count": len(visible),
					"unit_total": snapshot.UnitTotal, "unit_omitted": snapshot.UnitOmitted,
					"payload_bytes": len(m.Payload), "decode_us": (decodedNS - decodeNS) / 1000,
					"transform_us": (transformNS - decodedNS) / 1000})
				_ = s.emit(s.park, "combat.snapshot", m.Session, s.registry.Revision, snapshot)
				perf.event("snapshot_forward", map[string]any{"session": m.Session, "seq": snapshot.Seq,
					"bw_tick": snapshot.BWTick, "duration_us": (monoNS() - transformNS) / 1000})
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
	if s.nativePatchReport("controller", m) {
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
	case "building.state":
		var state struct {
			ID              string `json:"id"`
			NativeID        string `json:"native_id"`
			Owner           int    `json:"owner"`
			Race            string `json:"race"`
			Completed       bool   `json:"completed"`
			Health          int    `json:"health"`
			MaxHealth       int    `json:"max_health,omitempty"`
			Queue           int    `json:"queue"`
			RemainingFrames int    `json:"remaining_frames"`
			Minerals        int    `json:"minerals"`
			Gas             *int   `json:"gas"`
			Availability    map[string]struct {
				Ready       bool   `json:"ready"`
				Reason      string `json:"reason"`
				Requirement string `json:"requirement"`
			} `json:"availability"`
			Commands []struct {
				Slot        int    `json:"slot"`
				Action      string `json:"action"`
				UnitType    string `json:"unit_type"`
				Label       string `json:"label"`
				Ready       bool   `json:"ready"`
				Reason      string `json:"reason"`
				Requirement string `json:"requirement"`
			} `json:"commands"`
			LarvaCount           *int `json:"larva_count,omitempty"`
			MorphCount           *int `json:"morph_count,omitempty"`
			MorphRemainingFrames *int `json:"morph_remaining_frames,omitempty"`
			SupplyProvided       *int `json:"supply_provided,omitempty"`
			SupplyUsed           int  `json:"supply_used"`
			SupplyTotal          int  `json:"supply_total"`
			CommandAuthorized    bool `json:"command_authorized"`
		}
		if m.Decode(&state) != nil {
			return
		}
		if p != nil && ((state.Owner == 0 && p != s.bw) ||
			(state.Owner != 0 && p != s.controller)) {
			s.ack(p, m, false, "wrong_native_owner")
			return
		}
		entity, exists := s.registry.Entities[state.ID]
		if m.Session != s.registry.Session || m.Revision != s.registry.Revision ||
			!exists || entity.Kind != "structure" || !supportedNativeBuilding(entity.Type) ||
			s.registry.Destroyed[state.ID] || s.proxies[state.ID] != state.NativeID ||
			entity.Owner != state.Owner || state.Health < 0 || state.Health > 1000000 ||
			(state.MaxHealth != 0 && (state.MaxHealth < state.Health || state.MaxHealth > 1000000)) ||
			state.Queue < 0 || state.Queue > 5 || state.RemainingFrames < 0 ||
			state.Minerals < 0 || state.Gas == nil || *state.Gas < 0 ||
			state.SupplyUsed < 0 || state.SupplyTotal < 0 {
			return
		}
		building, _ := world.SupportedBuilding(entity.Type)
		if (state.MaxHealth != 0 && state.MaxHealth != building.MaxHealth) ||
			state.Race != strings.SplitN(building.NativeType, "_", 2)[0] ||
			len(state.Availability) != len(building.Production) ||
			len(state.Commands) != len(building.Production) ||
			(state.LarvaCount != nil && (*state.LarvaCount < 0 || *state.LarvaCount > 3)) ||
			(state.MorphCount != nil && (*state.MorphCount < 0 || *state.MorphCount > 3)) ||
			(state.MorphRemainingFrames != nil && *state.MorphRemainingFrames < 0) ||
			(state.SupplyProvided != nil && *state.SupplyProvided < 0) {
			return
		}
		for slot, unitID := range building.Production {
			availability, ok := state.Availability[unitID]
			if !ok || availability.Reason == "" || len(availability.Reason) > 64 ||
				len(availability.Requirement) > 64 {
				return
			}
			command := state.Commands[slot]
			if command.Slot != slot || command.Action != "unit.train" ||
				command.UnitType != unitID || command.Label == "" || len(command.Label) > 64 ||
				command.Ready != availability.Ready || command.Reason != availability.Reason ||
				command.Requirement != availability.Requirement {
				return
			}
		}
		state.CommandAuthorized = s.mayOrderProduction(entity.Owner)
		_ = s.emit(s.park, "building.state", m.Session, m.Revision, state)
	case "player.resources":
		var resources struct {
			Owner       int  `json:"owner"`
			Minerals    int  `json:"minerals"`
			Gas         *int `json:"gas"`
			SupplyUsed  int  `json:"supply_used"`
			SupplyTotal int  `json:"supply_total"`
		}
		if m.Decode(&resources) != nil || m.Session != s.registry.Session ||
			m.Revision != s.registry.Revision || resources.Owner < 0 || resources.Owner > 15 ||
			resources.Minerals < 0 || resources.Gas == nil || *resources.Gas < 0 ||
			resources.SupplyUsed < 0 || resources.SupplyTotal < 0 {
			return
		}
		if p != nil && ((resources.Owner == 0 && p != s.bw) ||
			(resources.Owner != 0 && p != s.controller)) {
			s.ack(p, m, false, "wrong_native_owner")
			return
		}
		_ = s.emit(s.park, "player.resources", m.Session, m.Revision, resources)
	case "world.ack":
		var answer world.Ack
		if m.Decode(&answer) != nil || m.Session != s.registry.Session {
			return
		}
		link, exists := s.pendingLinks[answer.OpID]
		if !exists {
			return
		}
		delete(s.pendingLinks, answer.OpID)
		if !answer.Accepted {
			if link.Revision < s.registry.Revision || s.parkPatch != nil || s.targetPatch != nil {
				// The ordered navigation update overtook this health link.
				if s.deferredLinks == nil {
					s.deferredLinks = map[string]bool{}
				}
				s.deferredLinks[link.ID] = true
				s.publishReady()
				return
			}
			s.ready = false
			s.pendingReady = nil
			log.Printf("controller target link rejected revision=%d: %s", link.Revision, answer.Error)
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
		if p != nil {
			expected := s.controller
			if command.Verb == "unit.train" && s.registry.Entities[command.TargetID].Owner == 0 {
				expected = s.bw
			}
			if p != expected {
				s.ack(p, m, false, "wrong_native_owner")
				return
			}
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
			s.pendingLinks = map[string]pendingTargetLink{}
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
		spawnJournalPath: *spawnJournal, maxLiveActors: *maxLiveActors,
		parkSupervisorSocket: os.Getenv("BRIDGE_PARK_SUPERVISOR_SOCKET"),
		parkGeneration:       os.Getenv("BRIDGE_PARK_GENERATION")}
	log.Printf("world.v1 listening park=%s openbw=%s controller=%s", *parkAddress, *bwAddress, *controllerAddress)
	go s.serve(bw, "bw")
	go s.serve(controller, "controller")
	s.serve(park, "park")
}
