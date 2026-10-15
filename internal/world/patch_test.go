package world

import (
	"errors"
	"strings"
	"testing"
)

func patchFixture(t *testing.T) (*Registry, Transform, Entity, Entity) {
	t.Helper()
	r := NewRegistry()
	ride := exampleEntity("openrct2:ride:17#1")
	if err := r.Replace("park-session", 1, 8, 8, []Entity{ride}, nil); err != nil {
		t.Fatal(err)
	}
	transform, err := Fit(8, 8, 8, 8)
	if err != nil {
		t.Fatal(err)
	}
	wall := Entity{ID: "openrct2:wall:3:0:0:0:0#1", Source: "openrct2",
		SourceID: "wall:3:0:0:0:0", Kind: "wall", Type: "wall", Position: Point{0, 0},
		Geometry: Geometry{Cells: []Point{{0, 0}}, Rects: []Rect{{0, 0, 4, 32}}},
		Combat:   Combat{Targetable: true, Health: 100}, Revision: 2}
	return r, transform, ride, wall
}

func TestStagePatchAtomicCommitAndRetry(t *testing.T) {
	r, transform, ride, wall := patchFixture(t)
	modified := ride
	modified.Revision = 2
	modified.Geometry.Rects = []Rect{{64, 96, 96, 32}}
	patch := Patch{ID: "patch:1", BaseRevision: 1, ResultRevision: 2,
		Additions: []Entity{wall}, Modifications: []Entity{modified},
		Terrain: []Terrain{{X: 0, Y: 0, Height: 0, Walkable: false}},
		Counts:  PatchCounts{Additions: 1, Modifications: 1, Terrain: 1}}
	candidate, mask, err := r.StagePatch("park-session", patch, DefaultMapping(), transform, 8, 8)
	if err != nil {
		t.Fatal(err)
	}
	if r.Revision != 1 || len(r.Entities) != 1 || len(r.Terrain) != 0 {
		t.Fatal("staging mutated confirmed registry")
	}
	if candidate.Entities[wall.ID].Combat.Health != 80 || !candidate.Entities[wall.ID].Collision.Blocks {
		t.Fatal("mapping was not applied before validation")
	}
	if mask.Hash == "" || !mask.BlockedPixel(0, 0) {
		t.Fatal("candidate navigation was not derived")
	}
	if err := r.CommitPatch(patch, candidate); err != nil {
		t.Fatal(err)
	}
	if r.Revision != 2 || len(r.Entities) != 2 || len(r.Terrain) != 1 {
		t.Fatal("patch did not commit atomically")
	}
	_, _, err = r.StagePatch("park-session", patch, DefaultMapping(), transform, 8, 8)
	if !errors.Is(err, ErrPatchDuplicate) {
		t.Fatalf("retry: %v", err)
	}
	patch.Additions[0].Type = "different"
	_, _, err = r.StagePatch("park-session", patch, DefaultMapping(), transform, 8, 8)
	if err == nil || err.Error() != "conflicting_patch_id" {
		t.Fatalf("conflicting retry: %v", err)
	}
}

func TestStagePatchRejectsIncompleteConflictingAndInvalidChanges(t *testing.T) {
	r, transform, ride, wall := patchFixture(t)
	good := Patch{ID: "patch:2", BaseRevision: 1, ResultRevision: 2,
		Additions: []Entity{wall}, Counts: PatchCounts{Additions: 1}}
	cases := []struct {
		name   string
		change func(*Patch)
		reason string
	}{
		{"stale base", func(p *Patch) { p.BaseRevision = 3; p.ResultRevision = 4; p.Additions[0].Revision = 4 }, "stale_base_revision"},
		{"partial transmission", func(p *Patch) { p.Counts.Additions = 2 }, "invalid_patch_counts"},
		{"conflicting operation", func(p *Patch) { p.Removals = []string{wall.ID}; p.Counts.Removals = 1 }, "invalid_or_conflicting_removal"},
		{"duplicate addition", func(p *Patch) { p.Additions = append(p.Additions, wall); p.Counts.Additions = 2 }, "invalid_or_conflicting_entity"},
		{"invalid geometry", func(p *Patch) { p.Additions[0].Geometry.Rects[0].X = 256 }, "invalid_mapped_entity"},
		{"reused source ID", func(p *Patch) { p.Additions[0].SourceID = ride.SourceID }, "source_identity_conflict"},
		{"invalid terrain", func(p *Patch) { p.Terrain = []Terrain{{X: 0, Y: 0, Slope: 64}}; p.Counts.Terrain = 1 }, "unsupported_terrain"},
	}
	for _, test := range cases {
		t.Run(test.name, func(t *testing.T) {
			patch := good
			patch.Additions = append([]Entity(nil), good.Additions...)
			patch.Additions[0] = cloneEntity(patch.Additions[0])
			test.change(&patch)
			_, _, err := r.StagePatch("park-session", patch, DefaultMapping(), transform, 8, 8)
			if err == nil || !strings.Contains(err.Error(), test.reason) {
				t.Fatalf("got %v, want %s", err, test.reason)
			}
			if r.Revision != 1 || len(r.Entities) != 1 {
				t.Fatal("failed patch modified confirmed state")
			}
		})
	}
}

func TestStagePatchManualRemovalPreservesCombatHistory(t *testing.T) {
	r, transform, ride, _ := patchFixture(t)
	r.Destroyed["old-target"] = true
	r.RemovalState["old-target"] = "removal_confirmed"
	patch := Patch{ID: "patch:remove", BaseRevision: 1, ResultRevision: 2,
		Removals: []string{ride.ID}, Counts: PatchCounts{Removals: 1}}
	candidate, _, err := r.StagePatch("park-session", patch, DefaultMapping(), transform, 8, 8)
	if err != nil {
		t.Fatal(err)
	}
	if candidate.Destroyed[ride.ID] || candidate.RemovalState[ride.ID] != "manual_removed" ||
		!candidate.Destroyed["old-target"] || candidate.RemovalState["old-target"] != "removal_confirmed" {
		t.Fatal("manual removal changed combat demolition history")
	}
}
