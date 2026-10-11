package main

import (
	"log"
	"net/http"
	"os"
	"path/filepath"
	"runtime"
	"strconv"

	"starcoaster/internal/artifacts"
	"starcoaster/internal/viewer"
)

func main() {
	_, source, _, _ := runtime.Caller(0)
	root := os.Getenv("STARCOASTER_ARTIFACT_ROOT")
	if root == "" {
		root = filepath.Join(filepath.Dir(source), "..", "..", "run-data", "artifacts")
	}
	listen := os.Getenv("STARCOASTER_VIEWER_LISTEN")
	if listen == "" {
		listen = "127.0.0.1:8787"
	}
	maxRuns := 0
	if raw := os.Getenv("STARCOASTER_VIEWER_MAX_RUNS"); raw != "" {
		var err error
		maxRuns, err = strconv.Atoi(raw)
		if err != nil || maxRuns < 0 {
			log.Fatal("invalid STARCOASTER_VIEWER_MAX_RUNS")
		}
	}
	store, err := artifacts.New(root)
	if err != nil {
		log.Fatal(err)
	}
	server, err := viewer.New(store, maxRuns)
	if err != nil {
		log.Fatal(err)
	}
	log.Printf("viewer listening on %s; artifacts %s", listen, store.Root)
	log.Fatal(http.ListenAndServe(listen, server.Handler()))
}
