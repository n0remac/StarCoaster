package world

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
)

// Patch is one bounded, ordered change to the authoritative park definition.
// Receipt and staging do not make its ResultRevision active.
type Patch struct {
	ID             string      `json:"patch_id"`
	BaseRevision   uint64      `json:"base_revision"`
	ResultRevision uint64      `json:"result_revision"`
	Additions      []Entity    `json:"additions"`
	Modifications  []Entity    `json:"modifications"`
	Removals       []string    `json:"removals"`
	Terrain        []Terrain   `json:"terrain"`
	Counts         PatchCounts `json:"counts"`
}

type PatchCounts struct {
	Additions     int `json:"additions"`
	Modifications int `json:"modifications"`
	Removals      int `json:"removals"`
	Terrain       int `json:"terrain"`
}

var ErrPatchDuplicate = errors.New("duplicate_patch")

func (p Patch) Digest() string {
	data, _ := json.Marshal(p)
	sum := sha256.Sum256(data)
	return hex.EncodeToString(sum[:])
}

func (p Patch) validateShape() error {
	if !identifier.MatchString(p.ID) || p.BaseRevision == 0 || p.ResultRevision != p.BaseRevision+1 {
		return errors.New("invalid_patch_identity_or_revision")
	}
	if p.Counts != (PatchCounts{len(p.Additions), len(p.Modifications), len(p.Removals), len(p.Terrain)}) {
		return errors.New("invalid_patch_counts")
	}
	if p.Counts.Additions+p.Counts.Modifications+p.Counts.Removals+p.Counts.Terrain > 4096 {
		return errors.New("patch_operation_limit")
	}
	if p.Counts.Additions+p.Counts.Modifications+p.Counts.Removals+p.Counts.Terrain == 0 {
		return errors.New("empty_patch")
	}
	return nil
}

// StagePatch validates the complete candidate without touching the confirmed
// registry. Call CommitPatch only after the required native application reports.
func (r *Registry) StagePatch(session string, p Patch, mapping Mapping, transform Transform,
	bwWidth, bwHeight int) (*Registry, NavigationMask, error) {
	if session != r.Session || session == "" {
		return nil, NavigationMask{}, errors.New("stale_session")
	}
	if err := p.validateShape(); err != nil {
		return nil, NavigationMask{}, err
	}
	digest := p.Digest()
	if old, ok := r.AppliedPatches[p.ID]; ok {
		if old == digest {
			return nil, NavigationMask{}, ErrPatchDuplicate
		}
		return nil, NavigationMask{}, errors.New("conflicting_patch_id")
	}
	if p.BaseRevision != r.Revision {
		return nil, NavigationMask{}, errors.New("stale_base_revision")
	}
	entities := make(map[string]Entity, len(r.Entities)+len(p.Additions))
	sources := make(map[string]string, len(r.Entities)+len(p.Additions))
	for id, entity := range r.Entities {
		entities[id] = cloneEntity(entity)
		sources[entity.SourceID] = id
	}
	touched := make(map[string]bool, len(p.Additions)+len(p.Modifications)+len(p.Removals))
	for _, id := range p.Removals {
		if !identifier.MatchString(id) || touched[id] || entities[id].ID == "" {
			return nil, NavigationMask{}, errors.New("invalid_or_conflicting_removal")
		}
		touched[id] = true
		delete(sources, entities[id].SourceID)
		delete(entities, id)
	}
	for _, operation := range []struct {
		items    []Entity
		addition bool
	}{
		{p.Additions, true}, {p.Modifications, false},
	} {
		for _, supplied := range operation.items {
			if touched[supplied.ID] || supplied.Source != "openrct2" || supplied.Revision != p.ResultRevision {
				return nil, NavigationMask{}, errors.New("invalid_or_conflicting_entity")
			}
			previous, exists := entities[supplied.ID]
			if operation.addition && (r.Destroyed[supplied.ID] || r.RemovalState[supplied.ID] != "") {
				return nil, NavigationMask{}, errors.New("retired_entity_id")
			}
			if exists == operation.addition {
				return nil, NavigationMask{}, errors.New("invalid_entity_lifecycle")
			}
			if exists && (previous.SourceID != supplied.SourceID || previous.Kind != supplied.Kind) {
				return nil, NavigationMask{}, errors.New("identity_changed")
			}
			if operation.addition {
				if sources[supplied.SourceID] != "" {
					return nil, NavigationMask{}, errors.New("source_identity_conflict")
				}
			}
			mapped := mapping.Apply(supplied)
			if err := mapped.Validate(r.Width, r.Height); err != nil {
				return nil, NavigationMask{}, fmt.Errorf("invalid_mapped_entity %s: %w", supplied.ID, err)
			}
			entities[supplied.ID] = cloneEntity(mapped)
			sources[supplied.SourceID] = supplied.ID
			touched[supplied.ID] = true
		}
	}
	terrain := append([]Terrain(nil), r.Terrain...)
	for i := range terrain {
		terrain[i] = cloneTerrain(terrain[i])
	}
	terrainIndex := make(map[Point]int, len(terrain))
	for i, cell := range terrain {
		terrainIndex[Point{cell.X, cell.Y}] = i
	}
	seenTerrain := map[Point]bool{}
	for _, cell := range p.Terrain {
		point := Point{cell.X, cell.Y}
		if seenTerrain[point] || cell.X < 0 || cell.Y < 0 || cell.X >= r.Width || cell.Y >= r.Height {
			return nil, NavigationMask{}, errors.New("invalid_or_duplicate_terrain")
		}
		if err := cell.ValidateGeometry(); err != nil {
			return nil, NavigationMask{}, fmt.Errorf("unsupported_terrain at %d,%d: %w", cell.X, cell.Y, err)
		}
		seenTerrain[point] = true
		if index, exists := terrainIndex[point]; exists {
			terrain[index] = cloneTerrain(cell)
		} else {
			terrainIndex[point] = len(terrain)
			terrain = append(terrain, cloneTerrain(cell))
		}
	}
	values := make([]Entity, 0, len(entities))
	for _, entity := range entities {
		values = append(values, entity)
	}
	candidate := NewRegistry()
	if err := candidate.Replace(session, p.ResultRevision, r.Width, r.Height, values, terrain); err != nil {
		return nil, NavigationMask{}, err
	}
	for id, destroyed := range r.Destroyed {
		candidate.Destroyed[id] = destroyed
	}
	for id, state := range r.RemovalState {
		candidate.RemovalState[id] = state
	}
	for _, id := range p.Removals {
		candidate.RemovalState[id] = "manual_removed"
	}
	for id, ack := range r.Seen {
		candidate.Seen[id] = ack
	}
	for id, old := range r.AppliedPatches {
		candidate.AppliedPatches[id] = old
	}
	mask, err := DeriveNavigation(candidate, transform, bwWidth, bwHeight)
	if err != nil {
		return nil, NavigationMask{}, err
	}
	return candidate, mask, nil
}

func (r *Registry) CommitPatch(p Patch, candidate *Registry) error {
	if candidate == nil || candidate.Session != r.Session || candidate.Revision != p.ResultRevision ||
		p.BaseRevision != r.Revision {
		return errors.New("stale_patch_commit")
	}
	candidate.AppliedPatches[p.ID] = p.Digest()
	*r = *candidate
	return nil
}
