package world

import (
	"bytes"
	"encoding/json"
	"fmt"
	"os"
	"strings"
)

// Scenario supplies the small amount of game-specific state needed by the
// bridge. Park objects are still discovered from the authoritative snapshot.
type Scenario struct {
	Version       int    `json:"version"`
	ID            string `json:"scenario_id"`
	Mode          string `json:"mode,omitempty"`
	DisplayName   string `json:"display_name"`
	ParkFile      string `json:"park_file"`
	ParkSize      [2]int `json:"park_size"`
	StartingUnits struct {
		Marines   [][2]int `json:"marines"`
		Zerglings [][2]int `json:"zerglings"`
	} `json:"starting_units"`
	ProductionFixture struct {
		TerranMinerals    int    `json:"terran_minerals,omitempty"`
		TerranGas         int    `json:"terran_gas,omitempty"`
		NativeSupplyDepot [2]int `json:"native_supply_depot,omitempty"`
		ZergMinerals      int    `json:"zerg_minerals,omitempty"`
		ZergGas           int    `json:"zerg_gas,omitempty"`
		NativeOverlord    [2]int `json:"native_overlord,omitempty"`
	} `json:"production_fixture,omitempty"`
	InitialStructures []ScenarioStructure `json:"initial_structures,omitempty"`
	// Native owners whose production the scenario commander may order. An
	// absent list retains ordinary Terran-only player control.
	ProductionControlOwners []int               `json:"production_control_owners,omitempty"`
	Objectives              []ScenarioObjective `json:"objectives"`
	InitialAI               struct {
		Strategy    string `json:"strategy"`
		Objective   string `json:"objective"`
		DelayFrames int    `json:"delay_frames"`
	} `json:"initial_ai"`
	Victory struct {
		AllWavesCleared        bool   `json:"all_waves_cleared,omitempty"`
		AllZerglingsEliminated bool   `json:"all_zerglings_eliminated"`
		ObjectiveIntact        string `json:"objective_intact"`
	} `json:"victory"`
	Defeat struct {
		ObjectiveDestroyed   string `json:"objective_destroyed"`
		AllMarinesEliminated bool   `json:"all_marines_eliminated"`
	} `json:"defeat"`
	SpawnWaves         []SpawnWave          `json:"spawn_waves,omitempty"`
	SpawnZones         map[string]SpawnZone `json:"spawn_zones,omitempty"`
	Waves              []ScenarioWave       `json:"waves,omitempty"`
	ParkDefense        *ParkDefenseWaves    `json:"park_defense,omitempty"`
	UnlimitedResources bool                 `json:"unlimited_resources,omitempty"`
}

// ScenarioStructure uses OpenRCT2 tile coordinates, before native map padding.
type ScenarioStructure struct {
	ID      string `json:"id"`
	Type    string `json:"type"`
	Faction string `json:"faction"`
	Tile    [2]int `json:"tile"`
}

// ParkDefenseWaves is one recurring attack template. Frames follow the
// authoritative OpenBW simulation clock (42 ms per frame at normal speed).
type ParkDefenseWaves struct {
	InitialDelayFrames   int        `json:"initial_delay_frames"`
	IntervalFrames       int        `json:"interval_frames"`
	UnitsPerWave         int        `json:"units_per_wave"`
	ManualCooldownFrames int        `json:"manual_cooldown_frames"`
	SpawnZones           []string   `json:"spawn_zones"`
	WaveTiers            []WaveTier `json:"wave_tiers,omitempty"`
	ManualActivation     bool       `json:"manual_activation,omitempty"`
	FixedSpawn           bool       `json:"fixed_spawn,omitempty"`
}

type WaveTier struct {
	FromWave int             `json:"from_wave"`
	Groups   []WaveTierGroup `json:"groups"`
}

type WaveTierGroup struct {
	UnitType string `json:"unit_type"`
	Count    int    `json:"count"`
}

func SupportedEnemyWaveUnit(id string) bool {
	unit, ok := SupportedUnit(id)
	return ok && unit.Race == "zerg" && unit.Ownership == "enemy" && unit.Movement == "ground" && unit.Spawnable
}

func (p *ParkDefenseWaves) GroupsForWave(sequence int) []WaveTierGroup {
	if len(p.WaveTiers) == 0 {
		return []WaveTierGroup{{UnitType: "zerg_zergling", Count: p.UnitsPerWave}}
	}
	selected := p.WaveTiers[0].Groups
	for _, tier := range p.WaveTiers {
		if tier.FromWave > sequence {
			break
		}
		selected = tier.Groups
	}
	return selected
}

// Description is player-facing metadata. It is never evaluated as a script.
type ScenarioObjective struct {
	ID          string `json:"id"`
	Description string `json:"description,omitempty"`
	EntityKind  string `json:"entity_kind"`
	EntityType  string `json:"entity_type"`
	EntityName  string `json:"entity_name,omitempty"`
	Required    bool   `json:"required"`
}

type SpawnZone struct {
	Tiles [][2]int `json:"tiles"`
}
type WaveTrigger struct {
	Type   string `json:"type"`
	Frames *int   `json:"frames,omitempty"`
	WaveID string `json:"wave_id,omitempty"`
}
type WaveGroup struct {
	UnitType  string `json:"unit_type"`
	Count     int    `json:"count"`
	SpawnZone string `json:"spawn_zone"`
}
type ScenarioWave struct {
	ID      string      `json:"id"`
	Trigger WaveTrigger `json:"trigger"`
	Groups  []WaveGroup `json:"groups"`
}

// SpawnWave is a small trusted scenario request, not a player action.
type SpawnWave struct {
	ID        string `json:"id"`
	Trigger   string `json:"trigger"`
	UnitType  string `json:"unit_type"`
	Count     int    `json:"count"`
	X         int    `json:"x"`
	Y         int    `json:"y"`
	Formation string `json:"formation"`
}

func LoadScenario(path string) (*Scenario, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var scenario Scenario
	var header struct {
		Version int `json:"version"`
	}
	if err := json.Unmarshal(data, &header); err != nil {
		return nil, err
	}
	if header.Version == 2 {
		decoder := json.NewDecoder(bytes.NewReader(data))
		decoder.DisallowUnknownFields()
		if err := decoder.Decode(&scenario); err != nil {
			return nil, err
		}
	} else if err := json.Unmarshal(data, &scenario); err != nil {
		return nil, err
	}
	parkDefense := scenario.Mode == "park_defense"
	if (scenario.Version != 1 && scenario.Version != 2) || !identifier.MatchString(scenario.ID) || scenario.ParkSize[0] < 1 || scenario.ParkSize[1] < 1 ||
		scenario.ParkSize[0] > 256 || scenario.ParkSize[1] > 256 || (!parkDefense && len(scenario.StartingUnits.Marines) == 0) ||
		(!parkDefense && (len(scenario.StartingUnits.Zerglings) == 0 || len(scenario.Objectives) == 0 ||
			scenario.InitialAI.Strategy != "objective_assault" || scenario.InitialAI.Objective == "")) ||
		(parkDefense && (scenario.Version != 2 || len(scenario.StartingUnits.Zerglings) != 0 ||
			scenario.InitialAI.Strategy != "park_defense" || scenario.InitialAI.Objective != "")) ||
		scenario.InitialAI.DelayFrames < 0 || scenario.InitialAI.DelayFrames > 600 ||
		(!parkDefense && (!scenario.Victory.AllZerglingsEliminated || !scenario.Defeat.AllMarinesEliminated ||
			scenario.Victory.ObjectiveIntact != scenario.InitialAI.Objective ||
			scenario.Defeat.ObjectiveDestroyed != scenario.InitialAI.Objective)) ||
		(parkDefense && (scenario.Victory.AllWavesCleared || scenario.Victory.AllZerglingsEliminated ||
			scenario.Victory.ObjectiveIntact != "" || scenario.Defeat.AllMarinesEliminated ||
			scenario.Defeat.ObjectiveDestroyed != "")) ||
		(scenario.Mode != "" && scenario.Mode != "park_defense") {
		return nil, fmt.Errorf("invalid scenario configuration")
	}
	if scenario.ProductionFixture.TerranMinerals < 0 || scenario.ProductionFixture.TerranMinerals > 100000 ||
		scenario.ProductionFixture.TerranGas < 0 || scenario.ProductionFixture.TerranGas > 100000 ||
		scenario.ProductionFixture.ZergMinerals < 0 || scenario.ProductionFixture.ZergMinerals > 100000 ||
		scenario.ProductionFixture.ZergGas < 0 || scenario.ProductionFixture.ZergGas > 100000 ||
		(scenario.ProductionFixture.TerranMinerals > 0 &&
			(scenario.ProductionFixture.NativeSupplyDepot[0] < 1 || scenario.ProductionFixture.NativeSupplyDepot[0] > 252 ||
				scenario.ProductionFixture.NativeSupplyDepot[1] < 1 || scenario.ProductionFixture.NativeSupplyDepot[1] > 253)) ||
		(scenario.ProductionFixture.ZergMinerals > 0 &&
			(scenario.ProductionFixture.NativeOverlord[0] < 1 || scenario.ProductionFixture.NativeOverlord[0] > 254 ||
				scenario.ProductionFixture.NativeOverlord[1] < 1 || scenario.ProductionFixture.NativeOverlord[1] > 254)) {
		return nil, fmt.Errorf("invalid production fixture")
	}
	controlOwners := map[int]bool{}
	for _, owner := range scenario.ProductionControlOwners {
		if owner < 0 || owner > 15 || controlOwners[owner] {
			return nil, fmt.Errorf("invalid production control owner")
		}
		controlOwners[owner] = true
	}
	if scenario.ProductionFixture.TerranMinerals > 0 {
		x, y := scenario.ProductionFixture.NativeSupplyDepot[0], scenario.ProductionFixture.NativeSupplyDepot[1]
		parkX, parkY := (256-scenario.ParkSize[0])/2, (256-scenario.ParkSize[1])/2
		if x < parkX+scenario.ParkSize[0] && x+3 > parkX &&
			y < parkY+scenario.ParkSize[1] && y+2 > parkY && !scenario.UnlimitedResources {
			return nil, fmt.Errorf("production fixture overlaps mapped park")
		}
	}
	if scenario.ProductionFixture.ZergMinerals > 0 {
		x, y := scenario.ProductionFixture.NativeOverlord[0], scenario.ProductionFixture.NativeOverlord[1]
		parkX, parkY := (256-scenario.ParkSize[0])/2, (256-scenario.ParkSize[1])/2
		if x >= parkX && x < parkX+scenario.ParkSize[0] &&
			y >= parkY && y < parkY+scenario.ParkSize[1] {
			return nil, fmt.Errorf("production fixture overlaps mapped park")
		}
	}
	for _, objective := range scenario.Objectives {
		if !identifier.MatchString(objective.ID) || objective.EntityKind == "" || objective.EntityType == "" {
			return nil, fmt.Errorf("invalid scenario objective")
		}
	}
	if scenario.Version == 2 {
		if err := scenario.validateV2(); err != nil {
			return nil, err
		}
		return &scenario, nil
	}
	if len(scenario.SpawnWaves) > 4 {
		return nil, fmt.Errorf("too many scenario spawn waves")
	}
	seenWave := map[string]bool{}
	for _, wave := range scenario.SpawnWaves {
		if !identifier.MatchString(wave.ID) || seenWave[wave.ID] || wave.Trigger != "on_ready" ||
			wave.UnitType != "zerg_zergling" || wave.Count < 1 || wave.Count > 5 ||
			wave.Formation != "compact" || wave.X < 0 || wave.Y < 0 ||
			wave.X >= scenario.ParkSize[0]*32 || wave.Y >= scenario.ParkSize[1]*32 {
			return nil, fmt.Errorf("invalid scenario spawn wave")
		}
		seenWave[wave.ID] = true
	}
	return &scenario, nil
}

func (s *Scenario) validateV2() error {
	if strings.TrimSpace(s.DisplayName) == "" || strings.TrimSpace(s.ParkFile) == "" ||
		len(s.SpawnWaves) != 0 || (len(s.SpawnZones) == 0 &&
		(s.Mode != "park_defense" || s.ParkDefense == nil || !s.ParkDefense.FixedSpawn)) ||
		(s.Mode != "park_defense" && (!s.Victory.AllWavesCleared || len(s.Waves) == 0 || s.ParkDefense != nil)) ||
		(s.Mode == "park_defense" && (len(s.Waves) != 0 || s.ParkDefense == nil)) {
		return fmt.Errorf("invalid v2 scenario configuration")
	}
	objectives := map[string]bool{}
	for _, objective := range s.Objectives {
		if objectives[objective.ID] || strings.TrimSpace(objective.Description) == "" ||
			(objective.EntityName != "" && strings.TrimSpace(objective.EntityName) == "") {
			return fmt.Errorf("invalid or duplicate objective: %s", objective.ID)
		}
		objectives[objective.ID] = true
	}
	if s.Mode != "park_defense" && (!objectives[s.InitialAI.Objective] || !objectives[s.Victory.ObjectiveIntact] || !objectives[s.Defeat.ObjectiveDestroyed]) {
		return fmt.Errorf("unknown objective reference")
	}
	seenTiles := map[[2]int]bool{}
	for _, group := range [][][2]int{s.StartingUnits.Marines, s.StartingUnits.Zerglings} {
		for _, tile := range group {
			if !s.validTile(tile) || seenTiles[tile] {
				return fmt.Errorf("invalid or duplicate starting tile: %v", tile)
			}
			seenTiles[tile] = true
		}
	}
	structureIDs := map[string]bool{}
	structureTiles := map[[2]int]bool{}
	for _, structure := range s.InitialStructures {
		building, ok := SupportedBuilding(structure.Type)
		if !ok || !identifier.MatchString(structure.ID) || structureIDs[structure.ID] ||
			(structure.Faction != "terran" && structure.Faction != "zerg") ||
			!strings.EqualFold(strings.SplitN(building.NativeType, "_", 2)[0], structure.Faction) {
			return fmt.Errorf("invalid initial structure: %s", structure.ID)
		}
		structureIDs[structure.ID] = true
		for y := structure.Tile[1]; y < structure.Tile[1]+building.Height; y++ {
			for x := structure.Tile[0]; x < structure.Tile[0]+building.Width; x++ {
				tile := [2]int{x, y}
				if x < 8 || y < 8 || x >= s.ParkSize[0]-8 || y >= s.ParkSize[1]-8 ||
					seenTiles[tile] || structureTiles[tile] {
					return fmt.Errorf("invalid initial structure footprint: %s at %v", structure.ID, tile)
				}
				structureTiles[tile] = true
			}
		}
	}
	for id, zone := range s.SpawnZones {
		if !identifier.MatchString(id) || len(zone.Tiles) == 0 {
			return fmt.Errorf("invalid spawn zone: %s", id)
		}
		seen := map[[2]int]bool{}
		for _, tile := range zone.Tiles {
			if !s.validTile(tile) || seen[tile] || structureTiles[tile] {
				return fmt.Errorf("invalid or duplicate zone tile: %s %v", id, tile)
			}
			seen[tile] = true
		}
	}
	if s.Mode == "park_defense" {
		p := s.ParkDefense
		if p.InitialDelayFrames < 1 || p.IntervalFrames < 1 ||
			(len(p.WaveTiers) == 0 && (p.UnitsPerWave < 1 || p.UnitsPerWave > 64)) ||
			(len(p.WaveTiers) > 0 && p.UnitsPerWave != 0) ||
			p.ManualCooldownFrames < 0 || (p.FixedSpawn && (!p.ManualActivation || len(p.SpawnZones) != 0)) ||
			(!p.FixedSpawn && len(p.SpawnZones) < 2) {
			return fmt.Errorf("invalid park defense wave template")
		}
		previous := 0
		for _, tier := range p.WaveTiers {
			if (previous == 0 && tier.FromWave != 1) || tier.FromWave <= previous || len(tier.Groups) == 0 {
				return fmt.Errorf("invalid park defense wave tier threshold")
			}
			previous = tier.FromWave
			total := 0
			for _, group := range tier.Groups {
				if !SupportedEnemyWaveUnit(group.UnitType) || group.Count < 1 || group.Count > 64 {
					return fmt.Errorf("invalid park defense wave tier group")
				}
				total += group.Count
			}
			if total > 64 {
				return fmt.Errorf("park defense wave exceeds queue capacity")
			}
		}
		seen := map[string]bool{}
		for _, id := range p.SpawnZones {
			if seen[id] || s.SpawnZones[id].Tiles == nil {
				return fmt.Errorf("invalid park defense spawn zone: %s", id)
			}
			seen[id] = true
		}
		return nil
	}
	waves := map[string]ScenarioWave{}
	for _, wave := range s.Waves {
		if !identifier.MatchString(wave.ID) || len(wave.Groups) == 0 || len(wave.Groups) > 64 || waves[wave.ID].ID != "" {
			return fmt.Errorf("invalid or duplicate wave: %s", wave.ID)
		}
		waves[wave.ID] = wave
		total := 0
		for _, group := range wave.Groups {
			if !SupportedEnemyWaveUnit(group.UnitType) || group.Count < 1 || group.Count > 64 || s.SpawnZones[group.SpawnZone].Tiles == nil {
				return fmt.Errorf("invalid group in wave: %s", wave.ID)
			}
			total += group.Count
		}
		if total > 64 {
			return fmt.Errorf("wave exceeds queue capacity: %s", wave.ID)
		}
		switch wave.Trigger.Type {
		case "on_ready":
			if wave.Trigger.Frames != nil || wave.Trigger.WaveID != "" {
				return fmt.Errorf("invalid on_ready trigger: %s", wave.ID)
			}
		case "elapsed_frames":
			if wave.Trigger.Frames == nil || *wave.Trigger.Frames < 0 || wave.Trigger.WaveID != "" {
				return fmt.Errorf("invalid elapsed_frames trigger: %s", wave.ID)
			}
		case "wave_cleared":
			if wave.Trigger.WaveID == "" || wave.Trigger.Frames != nil {
				return fmt.Errorf("invalid wave_cleared trigger: %s", wave.ID)
			}
		default:
			return fmt.Errorf("unknown wave trigger: %s", wave.Trigger.Type)
		}
	}
	visiting, visited := map[string]bool{}, map[string]bool{}
	var visit func(string) error
	visit = func(id string) error {
		if visiting[id] {
			return fmt.Errorf("circular wave dependency: %s", id)
		}
		if visited[id] {
			return nil
		}
		wave, ok := waves[id]
		if !ok {
			return fmt.Errorf("unknown wave reference: %s", id)
		}
		visiting[id] = true
		if wave.Trigger.Type == "wave_cleared" {
			if err := visit(wave.Trigger.WaveID); err != nil {
				return err
			}
		}
		visiting[id], visited[id] = false, true
		return nil
	}
	for id := range waves {
		if err := visit(id); err != nil {
			return err
		}
	}
	return nil
}

func (s *Scenario) validTile(tile [2]int) bool {
	return tile[0] >= 0 && tile[1] >= 0 && tile[0] < s.ParkSize[0] && tile[1] < s.ParkSize[1]
}

// Outcome uses only confirmed park demolition and complete OpenBW actor counts.
func (s *Scenario) Outcome(objectiveDestroyed bool, marines, enemies int) string {
	if s.Mode == "park_defense" {
		return ""
	}
	if objectiveDestroyed || marines == 0 {
		return "defeat"
	}
	if enemies == 0 {
		return "victory"
	}
	return ""
}

func (s *Scenario) CheckReady(registry *Registry, proxies map[string]string, ready Ready) error {
	return s.CheckReadyWithRuntime(registry, proxies, ready, 0, 0)
}

func (s *Scenario) CheckReadyWithRuntime(registry *Registry, proxies map[string]string, ready Ready,
	runtimeMarines, runtimeZerglings int) error {
	return s.CheckReadyWithRuntimeState(registry, proxies, ready, runtimeMarines, runtimeZerglings, false)
}

// A durable confirmed demolition permits terminal recovery without the ride
// reappearing in a fresh park snapshot.
func (s *Scenario) CheckReadyWithRuntimeState(registry *Registry, proxies map[string]string, ready Ready,
	runtimeMarines, runtimeZerglings int, objectiveDestroyed bool) error {
	if registry.Width != s.ParkSize[0] || registry.Height != s.ParkSize[1] {
		return fmt.Errorf("park_size_mismatch: expected %dx%d, got %dx%d", s.ParkSize[0], s.ParkSize[1], registry.Width, registry.Height)
	}
	if ready.Navigation != "native" {
		return fmt.Errorf("native_navigation_unavailable: %s", ready.Navigation)
	}
	validCounts := ready.Marines == len(s.StartingUnits.Marines) &&
		ready.Zerglings == len(s.StartingUnits.Zerglings)
	if ready.Resuming {
		validCounts = runtimeMarines >= 0 && runtimeZerglings >= 0 &&
			ready.Marines >= runtimeMarines && ready.Zerglings >= runtimeZerglings &&
			ready.Marines <= len(s.StartingUnits.Marines)+runtimeMarines &&
			ready.Zerglings <= len(s.StartingUnits.Zerglings)+runtimeZerglings
	}
	if !validCounts {
		return fmt.Errorf("starting_units_missing: marines=%d/%d zerglings=%d/%d", ready.Marines,
			len(s.StartingUnits.Marines), ready.Zerglings, len(s.StartingUnits.Zerglings))
	}
	for _, objective := range s.Objectives {
		if !objective.Required {
			continue
		}
		if objectiveDestroyed && objective.ID == s.Defeat.ObjectiveDestroyed {
			continue
		}
		id, err := s.ObjectiveEntityID(registry, objective.ID)
		if err != nil {
			return err
		}
		if proxies[id] == "" {
			return fmt.Errorf("objective_target_missing: %s", objective.ID)
		}
	}
	return nil
}

func (s *Scenario) ObjectiveEntityID(registry *Registry, objectiveID string) (string, error) {
	for _, objective := range s.Objectives {
		if objective.ID != objectiveID {
			continue
		}
		var match string
		count := 0
		for id, entity := range registry.Entities {
			if entity.Kind == objective.EntityKind && entity.Type == objective.EntityType &&
				(objective.EntityName == "" || entity.Name == objective.EntityName) && !registry.Destroyed[id] {
				match = id
				count++
			}
		}
		if count != 1 {
			return "", fmt.Errorf("objective_ambiguous_or_missing: %s matches=%d", objective.ID, count)
		}
		return match, nil
	}
	return "", fmt.Errorf("objective_not_configured: %s", objectiveID)
}
