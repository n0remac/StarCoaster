package main

import (
	"fmt"
	"os"
	"path/filepath"

	"starcoaster/internal/world"
)

func main() {
	if len(os.Args) != 2 {
		fmt.Fprintln(os.Stderr, "usage: validate-scenario <scenario-id-or-path>")
		os.Exit(2)
	}
	path := os.Args[1]
	if filepath.Base(path) == path {
		packaged := filepath.Join("scenarios", path, "scenario.json")
		if _, err := os.Stat(packaged); err == nil {
			path = packaged
		} else {
			path = filepath.Join("scenarios", path+".json")
		}
	}
	scenario, err := world.LoadScenario(path)
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	fmt.Printf("%s v%d: configuration valid; requires live geometry check\n", scenario.ID, scenario.Version)
}
