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
	if err := os.WriteFile(filepath.Join(dir, "index.html"), []byte("app"), 0600); err != nil {
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
	app, err := http.Get(server.URL + "/")
	if err != nil {
		t.Fatal(err)
	}
	app.Body.Close()
	if app.Header.Get("Cache-Control") != "no-store" {
		t.Fatalf("browser entrypoint may be cached: %v", app.Header)
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

func TestPrivateParkSessionStatus(t *testing.T) {
	path := filepath.Join(t.TempDir(), "supervisor.sock")
	listener, err := net.Listen("unix", path)
	if err != nil {
		t.Fatal(err)
	}
	backend := &http.Server{Handler: http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/state" {
			_, _ = io.WriteString(w, `{"phase":"ready","generation":"new","parks":["A.park"]}`)
			return
		}
		if r.URL.Path != "/load" {
			t.Errorf("unexpected supervisor path %q", r.URL.Path)
		}
		_, _ = io.WriteString(w, `{"phase":"preparing"}`)
	})}
	go func() { _ = backend.Serve(listener) }()
	defer backend.Close()
	server := httptest.NewServer(handler(t.TempDir(), "127.0.0.1:11753", nil, path))
	defer server.Close()
	response, err := http.Get(server.URL + "/private/park-session")
	if err != nil {
		t.Fatal(err)
	}
	var state struct {
		Phase      string `json:"phase"`
		Generation string `json:"generation"`
	}
	if err := json.NewDecoder(response.Body).Decode(&state); err != nil {
		t.Fatal(err)
	}
	response.Body.Close()
	if response.StatusCode != http.StatusOK || state.Phase != "ready" || state.Generation != "new" ||
		response.Header.Get("Cache-Control") != "private, no-store" {
		t.Fatalf("incorrect park status: %d %+v", response.StatusCode, state)
	}
	post, err := http.Post(server.URL+"/private/park-session", "application/json", strings.NewReader("{}"))
	if err != nil {
		t.Fatal(err)
	}
	post.Body.Close()
	if post.StatusCode != http.StatusMethodNotAllowed {
		t.Fatalf("browser could modify park session: %d", post.StatusCode)
	}
	loadURL := server.URL + "/private/park-session/load"
	makeRequest := func(origin string) int {
		req, _ := http.NewRequest(http.MethodPost, loadURL, strings.NewReader(`{"park":"A.park"}`))
		if origin != "" {
			req.Header.Set("Origin", origin)
		}
		res, err := http.DefaultClient.Do(req)
		if err != nil {
			t.Fatal(err)
		}
		defer res.Body.Close()
		return res.StatusCode
	}
	if got := makeRequest(""); got != http.StatusForbidden {
		t.Fatalf("missing-origin load status %d", got)
	}
	if got := makeRequest("https://other.example"); got != http.StatusForbidden {
		t.Fatalf("cross-origin load status %d", got)
	}
	if got := makeRequest(server.URL); got != http.StatusAccepted && got != http.StatusOK {
		t.Fatalf("same-origin load without token status %d", got)
	}
}

func TestPrivateSaveUploadForwardsOnlyToSupervisor(t *testing.T) {
	directory, err := os.MkdirTemp("", "sc-sock-")
	if err != nil {
		t.Fatal(err)
	}
	defer os.RemoveAll(directory)
	path := filepath.Join(directory, "s")
	listener, err := net.Listen("unix", path)
	if err != nil {
		t.Fatal(err)
	}
	backend := &http.Server{Handler: http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/upload" || r.Header.Get("X-StarCoaster-Filename") != "selected.sv6" {
			t.Errorf("unexpected upload metadata: %s %s", r.URL.Path, r.Header.Get("X-StarCoaster-Filename"))
		}
		bytes, _ := io.ReadAll(r.Body)
		if string(bytes) != "save bytes" {
			t.Errorf("upload body changed: %q", bytes)
		}
		w.WriteHeader(http.StatusAccepted)
		_, _ = io.WriteString(w, `{"park":"private-id.sv6"}`)
	})}
	go func() { _ = backend.Serve(listener) }()
	defer backend.Close()
	server := httptest.NewServer(handler(t.TempDir(), "127.0.0.1:11753", nil, path))
	defer server.Close()
	request := func(origin string) int {
		req, _ := http.NewRequest(http.MethodPost, server.URL+"/private/park-session/upload", strings.NewReader("save bytes"))
		req.Header.Set("Origin", origin)
		req.Header.Set("X-StarCoaster-Filename", "selected.sv6")
		res, err := http.DefaultClient.Do(req)
		if err != nil {
			t.Fatal(err)
		}
		defer res.Body.Close()
		return res.StatusCode
	}
	if got := request("https://other.example"); got != http.StatusForbidden {
		t.Fatalf("cross-origin upload: %d", got)
	}
	if got := request(server.URL); got != http.StatusAccepted {
		t.Fatalf("same-origin upload without token: %d", got)
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
