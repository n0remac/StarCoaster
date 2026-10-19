package main

import (
	"encoding/json"
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
	server := httptest.NewServer(handler(dir, tcp.Addr().String(), nil))
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

func TestPrivateLicensedProvisioning(t *testing.T) {
	root := t.TempDir()
	for name, contents := range map[string]string{
		"Data/ch.dat": "licensed game data", "ObjData/ride.dat": "object data",
	} {
		path := filepath.Join(root, filepath.FromSlash(name))
		if err := os.MkdirAll(filepath.Dir(path), 0700); err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(path, []byte(contents), 0600); err != nil {
			t.Fatal(err)
		}
	}
	assets, err := loadLicensedAssets(root)
	if err != nil {
		t.Fatal(err)
	}
	server := httptest.NewServer(handler(t.TempDir(), "127.0.0.1:11753", assets))
	defer server.Close()
	response, err := http.Get(server.URL + "/private/rct2/manifest.json")
	if err != nil {
		t.Fatal(err)
	}
	var manifest licensedManifest
	if err := json.NewDecoder(response.Body).Decode(&manifest); err != nil {
		t.Fatal(err)
	}
	response.Body.Close()
	if response.StatusCode != http.StatusOK || manifest.Schema != 1 || len(manifest.Files) != 2 ||
		len(manifest.Version) != 64 || response.Header.Get("Cache-Control") != "private, no-store" {
		t.Fatalf("private RCT2 manifest invalid: status=%d manifest=%+v", response.StatusCode, manifest)
	}
	response, err = http.Get(server.URL + "/private/rct2/files/Data/ch.dat")
	if err != nil {
		t.Fatal(err)
	}
	contents, err := io.ReadAll(response.Body)
	response.Body.Close()
	if err != nil || response.StatusCode != http.StatusOK || string(contents) != "licensed game data" ||
		response.Header.Get("Cross-Origin-Embedder-Policy") != "require-corp" {
		t.Fatalf("private RCT2 file invalid: status=%d data=%q err=%v", response.StatusCode, contents, err)
	}
	response, err = http.Get(server.URL + "/private/rct2/files/unlisted.dat")
	if err != nil {
		t.Fatal(err)
	}
	response.Body.Close()
	if response.StatusCode != http.StatusNotFound {
		t.Fatalf("unlisted RCT2 file status=%d", response.StatusCode)
	}
	withoutAssets := httptest.NewServer(handler(t.TempDir(), "127.0.0.1:11753", nil))
	defer withoutAssets.Close()
	response, err = http.Get(withoutAssets.URL + "/private/rct2/manifest.json")
	if err != nil {
		t.Fatal(err)
	}
	response.Body.Close()
	if response.StatusCode != http.StatusNotFound {
		t.Fatalf("unconfigured RCT2 manifest status=%d", response.StatusCode)
	}
}

func TestLoopbackOnly(t *testing.T) {
	for _, address := range []string{"0.0.0.0:8080", "example.com:11753", "192.0.2.1:11753"} {
		if err := loopbackAddress(address); err == nil {
			t.Errorf("accepted %s", address)
		}
	}
}

func TestPublicFunnelTarget(t *testing.T) {
	config := []byte(`{"AllowFunnel":{"pi.example.ts.net:443":true},"Web":{"pi.example.ts.net:443":{"Handlers":{"/":{"Proxy":"http://127.0.0.1:8080"}}}}}`)
	for _, test := range []struct {
		listen string
		public bool
	}{
		{"127.0.0.1:8080", true},
		{"127.0.0.1:8091", false},
	} {
		public, err := funnelTargetsListen(config, test.listen)
		if err != nil || public != test.public {
			t.Errorf("listener %s: public=%t, err=%v", test.listen, public, err)
		}
	}
}
