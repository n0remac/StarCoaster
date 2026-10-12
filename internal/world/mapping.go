package world

import "strings"

type Rule struct {
	Kind         string   `json:"kind"`
	Type         string   `json:"type,omitempty"`
	Destructible *bool    `json:"destructible,omitempty"`
	Targetable   *bool    `json:"targetable,omitempty"`
	Blocks       *bool    `json:"blocks,omitempty"`
	Health       int      `json:"health,omitempty"`
	Owner        *int     `json:"owner,omitempty"`
	Armor        *int     `json:"armor,omitempty"`
	DamageScale  *float64 `json:"damage_scale,omitempty"`
	Effect       string   `json:"effect,omitempty"`
}
type Mapping struct {
	Rules []Rule `json:"rules"`
}

func DefaultMapping() Mapping {
	return Mapping{Rules: []Rule{
		{Kind: "terrain", Destructible: pointer(false), Targetable: pointer(false), Blocks: pointer(false)},
		{Kind: "guest", Destructible: pointer(false), Targetable: pointer(false), Blocks: pointer(false)},
		{Kind: "staff", Destructible: pointer(false), Targetable: pointer(false), Blocks: pointer(false)},
		{Kind: "path", Targetable: pointer(false), Blocks: pointer(false)},
		{Kind: "wall", Health: 80}, {Kind: "small_scenery", Health: 60}, {Kind: "large_scenery", Health: 160},
		{Kind: "ride", Health: 400}, {Kind: "shop", Health: 180}, {Kind: "facility", Health: 180},
	}}
}
func pointer[T any](v T) *T { return &v }
func (m Mapping) Apply(e Entity) Entity {
	constructed := e.Kind != "terrain" && e.Kind != "guest" && e.Kind != "staff"
	e.Destructible = constructed
	e.Combat.Targetable = constructed && e.Kind != "path"
	e.Collision.Blocks = constructed && e.Kind != "path"
	if e.Combat.Health == 0 && constructed {
		e.Combat.Health = 100
	}
	if e.Combat.DamageScale == 0 {
		e.Combat.DamageScale = 1
	}
	for _, r := range m.Rules {
		if r.Kind != e.Kind || (r.Type != "" && !strings.EqualFold(r.Type, e.Type)) {
			continue
		}
		if r.Destructible != nil {
			e.Destructible = *r.Destructible
		}
		if r.Targetable != nil {
			e.Combat.Targetable = *r.Targetable
		}
		if r.Blocks != nil {
			e.Collision.Blocks = *r.Blocks
		}
		if r.Health > 0 {
			e.Combat.Health = r.Health
		}
		if r.Owner != nil {
			e.Owner = *r.Owner
		}
		if r.Armor != nil {
			e.Combat.Armor = *r.Armor
		}
		if r.DamageScale != nil {
			e.Combat.DamageScale = *r.DamageScale
		}
		if r.Effect != "" {
			e.Removal.Effect = r.Effect
		}
	}
	if !e.Destructible {
		e.Combat.Targetable = false
	}
	return e
}
