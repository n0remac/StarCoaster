package world

import (
	"encoding/json"
	"testing"
)

func TestCollisionGeometryValidationCopyAndTransform(t *testing.T) {
	e := exampleEntity("openrct2:ride:7#1")
	e.Collision = Collision{Blocks: true, Mode: "height_aware", Volumes: []CollisionVolume{
		{Rect: Rect{64, 96, 32, 32}, BaseZ: 160, ClearanceZ: 176, OccupiedQuadrants: 15, Classification: "physical"},
		{Rect: Rect{32, 96, 32, 32}, BaseZ: 112, ClearanceZ: 144, OccupiedQuadrants: 3, Classification: "approximate"},
	}}
	if err := e.Validate(8, 8); err != nil {
		t.Fatal(err)
	}
	r := NewRegistry()
	if err := r.Replace("nav", 1, 8, 8, []Entity{e}, nil); err != nil {
		t.Fatal(err)
	}
	e.Collision.Volumes[0].BaseZ = 0
	stored := r.Entities[e.ID]
	if stored.Collision.Volumes[0].Rect.X != 32 || stored.Collision.Volumes[1].BaseZ != 160 {
		t.Fatal("volumes were not copied and sorted")
	}
	transform, _ := Fit(8, 8, 12, 12)
	native := transform.Entity(stored)
	if native.Collision.Volumes[0].Rect.X != 96 || native.Collision.Volumes[0].Rect.Y != 160 ||
		native.Collision.Volumes[0].BaseZ != 112 || stored.Collision.Volumes[0].Rect.X != 32 {
		t.Fatal("horizontal transform changed source or vertical height")
	}
	b, err := json.Marshal(stored)
	if err != nil {
		t.Fatal(err)
	}
	var decoded Entity
	if err := json.Unmarshal(b, &decoded); err != nil {
		t.Fatal(err)
	}
	if err := decoded.Validate(8, 8); err != nil {
		t.Fatal(err)
	}
	decoded.Collision.Volumes[0].OccupiedQuadrants = 0
	if decoded.Validate(8, 8) == nil {
		t.Fatal("invalid quadrant accepted")
	}
	decoded.Collision.Volumes = nil
	if decoded.Validate(8, 8) != nil {
		t.Fatal("explicit empty height-aware geometry rejected")
	}
	decoded.Collision.Mode = "legacy"
	decoded.Collision.Volumes = stored.Collision.Volumes
	if decoded.Validate(8, 8) == nil {
		t.Fatal("legacy volumes accepted")
	}
}
