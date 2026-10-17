package world

import (
	"path/filepath"
	"strings"
	"testing"
)

func TestFrontierScenarioRequiresNativeNavigationAndObjective(t *testing.T) {
	scenario, err := LoadScenario(filepath.Join("..", "..", "scenarios", "frontier-outpost", "scenario.json"))
	if err != nil {
		t.Fatal(err)
	}
	r := NewRegistry()
	e := exampleEntity("openrct2:ride:100#1")
	e.Kind, e.Type = "ride", "rct2.ride.mgr1"
	e.Name = "Frontier Carousel"
	if err := r.Replace("session-a", 1, 64, 64, []Entity{e}, nil); err != nil {
		t.Fatal(err)
	}
	ready := Ready{Navigation: "metadata_only", Marines: 6, Zerglings: 1}
	if err := scenario.CheckReady(r, map[string]string{e.ID: "openbw:7"}, ready); err == nil || !strings.Contains(err.Error(), "native_navigation_unavailable") {
		t.Fatalf("metadata-only navigation was accepted: %v", err)
	}
	ready.Navigation = "native"
	if err := scenario.CheckReady(r, nil, ready); err == nil || !strings.Contains(err.Error(), "objective_target_missing") {
		t.Fatalf("unmapped objective was accepted: %v", err)
	}
	if err := scenario.CheckReady(r, map[string]string{e.ID: "openbw:7"}, ready); err != nil {
		t.Fatal(err)
	}
	ready.Marines = 7
	if err := scenario.CheckReadyWithRuntime(r, map[string]string{e.ID: "openbw:7"}, ready, 1, 0); err == nil {
		t.Fatal("first readiness accepted an unexpected seventh Marine")
	}
	ready.Resuming = true
	if err := scenario.CheckReadyWithRuntime(r, map[string]string{e.ID: "openbw:7"}, ready, 1, 0); err != nil {
		t.Fatalf("reconciled runtime Marine prevented restart: %v", err)
	}
	ready.Marines = 8
	if err := scenario.CheckReadyWithRuntime(r, map[string]string{e.ID: "openbw:7"}, ready, 1, 0); err == nil {
		t.Fatal("unregistered extra Marine was accepted")
	}
	ready.Marines = 6
	ready.Resuming = false
	r.Width = 256
	if err := scenario.CheckReady(r, map[string]string{e.ID: "openbw:7"}, ready); err == nil || !strings.Contains(err.Error(), "park_size_mismatch") {
		t.Fatalf("oversized park was accepted: %v", err)
	}
}

func TestFrontierOutcomeUsesConfirmedState(t *testing.T) {
	scenario, err := LoadScenario(filepath.Join("..", "..", "scenarios", "frontier-outpost", "scenario.json"))
	if err != nil {
		t.Fatal(err)
	}
	for _, test := range []struct {
		destroyed bool
		marines   int
		zerglings int
		want      string
	}{{false, 6, 12, ""}, {false, 6, 0, "victory"}, {false, 0, 1, "defeat"},
		{true, 6, 0, "defeat"}} {
		if got := scenario.Outcome(test.destroyed, test.marines, test.zerglings); got != test.want {
			t.Fatalf("outcome %+v: %s", test, got)
		}
	}
}

func TestTrustedZergWaveScenario(t *testing.T) {
	scenario, err := LoadScenario(filepath.Join("..", "..", "tests", "fixtures", "frontier-outpost-zerg-wave.json"))
	if err != nil {
		t.Fatal(err)
	}
	if len(scenario.SpawnWaves) != 1 || scenario.SpawnWaves[0].UnitType != "zerg_zergling" ||
		scenario.SpawnWaves[0].Count != 5 || scenario.SpawnWaves[0].Trigger != "on_ready" {
		t.Fatalf("unexpected trusted wave: %+v", scenario.SpawnWaves)
	}
}
