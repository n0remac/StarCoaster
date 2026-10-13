package main

import (
	"bufio"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"hash/fnv"
	"net"
	"testing"

	"starcoaster/internal/world"
)

func TestNavigationMaskTransportIsBoundedAndDeterministic(t *testing.T) {
	s := testService()
	if err := s.registry.Replace("navigation-session", 1, 256, 256, nil, nil); err != nil {
		t.Fatal(err)
	}
	s.bwWidth, s.bwHeight = 256, 256
	s.transform, _ = world.Fit(256, 256, 256, 256)
	bridge, native := net.Pipe()
	defer bridge.Close()
	defer native.Close()
	done := make(chan struct{})
	go func() {
		s.sendNavigationMask(&peer{Conn: bridge}, 0)
		close(done)
	}()
	reader := bufio.NewReader(native)
	var packed []byte
	var hash string
	var chunks int
	for {
		line, err := reader.ReadBytes('\n')
		if err != nil {
			t.Fatal(err)
		}
		if len(line) >= 32768 {
			t.Fatalf("navigation protocol line exceeds native limit: %d", len(line))
		}
		var packet world.Envelope
		if err := json.Unmarshal(line, &packet); err != nil {
			t.Fatal(err)
		}
		switch packet.Kind {
		case "navigation.mask.begin":
			var begin struct {
				Hash   string `json:"hash"`
				Chunks int    `json:"chunks"`
			}
			if err := packet.Decode(&begin); err != nil {
				t.Fatal(err)
			}
			hash, chunks = begin.Hash, begin.Chunks
		case "navigation.mask.chunk":
			var chunk struct {
				Index int    `json:"index"`
				Hex   string `json:"hex"`
			}
			if err := packet.Decode(&chunk); err != nil || chunk.Index != len(packed)/6000 {
				t.Fatalf("invalid navigation chunk: %+v %v", chunk, err)
			}
			decoded, err := hex.DecodeString(chunk.Hex)
			if err != nil {
				t.Fatal(err)
			}
			packed = append(packed, decoded...)
		case "navigation.mask.end":
			<-done
			sum := fnv.New64a()
			_, _ = sum.Write(packed)
			if chunks != 22 || len(packed) != 131072 || hash != s.navigationMask.Hash ||
				hash != fmt.Sprintf("%016x", sum.Sum64()) {
				t.Fatalf("mask transport differs: chunks=%d bytes=%d hash=%s", chunks, len(packed), hash)
			}
			return
		default:
			t.Fatalf("unexpected navigation message %s", packet.Kind)
		}
	}
}
