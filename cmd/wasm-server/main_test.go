package main

import (
	"io"
	"net"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/gorilla/websocket"
)

func TestHeadersAndFixedGateway(t *testing.T) {
	dir := t.TempDir()
	if err := os.WriteFile(filepath.Join(dir, "client.wasm"), []byte("wasm"), 0600); err != nil {
		t.Fatal(err)
	}
	tcp, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	defer tcp.Close()
	go func() {
		for {
			conn, err := tcp.Accept()
			if err != nil {
				return
			}
			go func() { defer conn.Close(); _, _ = io.Copy(conn, conn) }()
		}
	}()
	server := httptest.NewServer(handler(dir, tcp.Addr().String()))
	defer server.Close()
	response, err := http.Get(server.URL + "/client.wasm")
	if err != nil {
		t.Fatal(err)
	}
	response.Body.Close()
	if response.Header.Get("Content-Type") != "application/wasm" ||
		response.Header.Get("Cross-Origin-Opener-Policy") != "same-origin" ||
		response.Header.Get("Cross-Origin-Embedder-Policy") != "require-corp" {
		t.Fatalf("browser response headers: %v", response.Header)
	}
	endpoint := "ws" + strings.TrimPrefix(server.URL, "http") + "/ws"
	_, denied, err := websocket.DefaultDialer.Dial(endpoint, http.Header{"Origin": []string{"https://other.example"}})
	if err == nil || denied == nil || denied.StatusCode != http.StatusForbidden {
		t.Fatalf("cross-origin gateway accepted: %v", err)
	}
	client, _, err := websocket.DefaultDialer.Dial(endpoint, http.Header{"Origin": []string{server.URL}})
	if err != nil {
		t.Fatal(err)
	}
	defer client.Close()
	payload := []byte{0, 1, 2, 3, 255}
	if err := client.WriteMessage(websocket.BinaryMessage, payload); err != nil {
		t.Fatal(err)
	}
	kind, returned, err := client.ReadMessage()
	if err != nil {
		t.Fatal(err)
	}
	if kind != websocket.BinaryMessage || string(returned) != string(payload) {
		t.Fatalf("gateway corrupted bytes: %v", returned)
	}
}

func TestLoopbackOnly(t *testing.T) {
	for _, address := range []string{"0.0.0.0:8080", "example.com:11753", "192.0.2.1:11753"} {
		if err := loopbackAddress(address); err == nil {
			t.Errorf("accepted %s", address)
		}
	}
}
