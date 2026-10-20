package main

import (
	"encoding/json"
	"os"
	"path/filepath"
	"sync"
	"syscall"
	"time"
	"unsafe"
)

// perf is deliberately a local, append-only diagnostic sink. The benchmark
// runner owns the directory and merges process files after shutdown.
var perf = newPerformanceSink()

type performanceSink struct {
	mu   sync.Mutex
	file *os.File
}

func newPerformanceSink() *performanceSink {
	dir := os.Getenv("STARCOASTER_PERF_DIR")
	if dir == "" {
		return &performanceSink{}
	}
	if err := os.MkdirAll(dir, 0750); err != nil {
		return &performanceSink{}
	}
	f, err := os.OpenFile(filepath.Join(dir, "bridge-events.jsonl"), os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0640)
	if err != nil {
		return &performanceSink{}
	}
	return &performanceSink{file: f}
}

func monoNS() int64 {
	var ts syscall.Timespec
	_, _, errno := syscall.RawSyscall(syscall.SYS_CLOCK_GETTIME, uintptr(1), uintptr(unsafe.Pointer(&ts)), 0)
	if errno != 0 {
		return 0
	}
	return ts.Sec*1e9 + ts.Nsec
}

func (p *performanceSink) event(stage string, fields map[string]any) {
	if p.file == nil {
		return
	}
	fields["source"] = "bridge"
	fields["stage"] = stage
	fields["mono_ns"] = monoNS()
	fields["wall_utc"] = time.Now().UTC().Format(time.RFC3339Nano)
	encoded, err := json.Marshal(fields)
	if err != nil {
		return
	}
	encoded = append(encoded, '\n')
	p.mu.Lock()
	_, _ = p.file.Write(encoded)
	p.mu.Unlock()
}
