package main

import (
	"bufio"
	"encoding/json"
	"flag"
	"fmt"
	"log"
	"net"
	"os"
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
	mu        sync.Mutex
	park, bw  *peer
	registry  *world.Registry
	mapping   world.Mapping
	stage     *staging
	next      uint64
	pending   map[string]world.CombatEvent
	proxies   map[string]string
	ready     bool
	bwWidth   int
	bwHeight  int
	transform world.Transform
	retired   map[string]bool
}

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
		if (role == "park" && s.park == p) || (role == "bw" && s.bw == p) {
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
	}
	s.mu.Unlock()
	_ = p.Close()
	log.Printf("%s disconnected: %v", role, scanner.Err())
}
func (s *service) handle(role string, p *peer, m world.Envelope) {
	if role == "park" {
		s.parkMessage(p, m)
	} else {
		s.bwMessage(p, m)
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
		s.stage = nil
		s.pending = map[string]world.CombatEvent{}
		s.proxies = map[string]string{}
		s.ack(p, m, true, "")
		log.Printf("park snapshot session=%s revision=%d entities=%d terrain=%d", m.Session, m.Revision, len(s.registry.Entities), len(s.registry.Terrain))
		s.forwardSnapshot()
	case "combat.result":
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
			s.registry.Revision = m.Revision
		}
		s.registry.RemovalState[result.EntityID] = result.State
		delete(s.pending, result.EventID)
		s.ack(p, m, true, "")
		_ = s.emit(s.bw, "combat.result", m.Session, s.registry.Revision, result)
		if result.State == "removal_confirmed" {
			_ = s.emit(s.bw, "navigation.obstacle.remove", m.Session, s.registry.Revision, map[string]string{"id": result.EntityID})
		}
	case "entity.upsert", "entity.remove", "entity.transform", "entity.state", "navigation.terrain.update":
		// The envelope and model are versioned for future live updates. Applying
		// one side before OpenBW accepts its geometry would split authority.
		s.ack(p, m, false, "live_update_unsupported")
	default:
		s.ack(p, m, false, "unsupported_operation")
	}
}
func (s *service) forwardSnapshot() {
	if s.bw == nil || s.registry.Session == "" {
		return
	}
	r := s.registry
	rev := r.Revision
	s.transform = world.Fit(r.Width, r.Height, s.bwWidth, s.bwHeight)
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
	if err := s.emit(s.bw, "world.snapshot.begin", r.Session, rev, world.SnapshotBegin{Width: derivedWidth, Height: derivedHeight, Chunks: len(chunks)}); err != nil {
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
	case "world.ack":
		var a world.Ack
		_ = m.Decode(&a)
		if !a.Accepted {
			log.Printf("OpenBW rejected %s: %s", a.OpID, a.Error)
			s.ready = false
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
		s.ready = true
		s.ack(p, m, true, "")
		_ = s.emit(s.park, "world.ready", m.Session, m.Revision, ready)
		log.Printf("OpenBW ready targets=%d unsupported=%d", ready.Targets, ready.UnsupportedTotal)
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
		s.registry.RemovalState[event.EntityID] = "destruction_requested"
		s.ack(p, m, true, "")
		if err := s.emit(s.park, "combat.event", m.Session, s.registry.Revision, event); err == nil {
			s.registry.RemovalState[event.EntityID] = "removal_pending"
		}
	case "entity.state":
		var payload struct {
			ID      string `json:"id"`
			ProxyID string `json:"proxy_id"`
		}
		if m.Decode(&payload) != nil || s.registry.Entities[payload.ID].ID == "" || payload.ProxyID == "" {
			s.ack(p, m, false, "unknown_entity")
			return
		}
		if previous := s.proxies[payload.ID]; previous != "" && previous != payload.ProxyID {
			s.ack(p, m, false, "proxy_identity_changed")
			return
		}
		s.proxies[payload.ID] = payload.ProxyID
		s.ack(p, m, true, "")
	case "combat.snapshot":
		if m.Session == s.registry.Session && s.ready && len(m.Payload) <= 32768 {
			var snapshot struct {
				Seq    uint64           `json:"seq"`
				BWTick int              `json:"bw_tick"`
				Units  []map[string]any `json:"units"`
			}
			if m.Decode(&snapshot) == nil {
				for _, unit := range snapshot.Units {
					if x, ok := unit["x"].(float64); ok {
						unit["x"] = s.transform.InversePixel(int(x))
					}
					if y, ok := unit["y"].(float64); ok {
						unit["y"] = s.transform.InversePixel(int(y))
					}
				}
				_ = s.emit(s.park, "combat.snapshot", m.Session, s.registry.Revision, snapshot)
			}
		}
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
		} else {
			if s.bw != nil {
				_ = s.bw.Close()
			}
			s.bw = p
			s.ready = false
		}
		s.mu.Unlock()
		log.Printf("%s connected", role)
		go s.consume(role, p)
	}
}
func main() {
	parkAddress := flag.String("park", "127.0.0.1:40010", "OpenRCT2 adapter listener")
	bwAddress := flag.String("openbw", "127.0.0.1:40011", "OpenBW adapter listener")
	rulesPath := flag.String("rules", "", "optional JSON mapping overrides")
	flag.Parse()
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
	s := &service{registry: world.NewRegistry(), mapping: mapping, pending: map[string]world.CombatEvent{}, proxies: map[string]string{}}
	log.Printf("world.v1 listening park=%s openbw=%s", *parkAddress, *bwAddress)
	go s.serve(bw, "bw")
	s.serve(park, "park")
}
