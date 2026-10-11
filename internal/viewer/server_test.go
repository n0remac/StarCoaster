package viewer

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"starcoaster/internal/artifacts"
)

func fixture(t *testing.T, root, id, kind, status string, video bool) {
	t.Helper()
	dir := filepath.Join(root, id)
	if err := os.Mkdir(dir, 0755); err != nil {
		t.Fatal(err)
	}
	run := artifacts.Run{SchemaVersion: 1, ID: id, Type: kind, Title: "Fixture " + status, Status: status, StartedAt: strings.TrimSuffix(id, "-abcdef123456") + "+00:00", Screenshots: []artifacts.File{{Path: "frame-015.png", Label: "Frame 15"}}, Videos: []artifacts.File{}, Logs: []artifacts.File{}}
	if kind == "live-capture" {
		run.Screenshots = []artifacts.File{{Path: "client-a-final.png", Label: "Client A"}}
	}
	os.WriteFile(filepath.Join(dir, run.Screenshots[0].Path), []byte("PNG"), 0644)
	if video {
		run.Videos = []artifacts.File{{Path: "combined.mp4", Label: "Combined"}}
		metadataName := "video-metadata.json"
		run.VideoMetadataFile = &metadataName
		os.WriteFile(filepath.Join(dir, "combined.mp4"), []byte("0123456789"), 0644)
		os.WriteFile(filepath.Join(dir, metadataName), []byte(`{"filename":"combined.mp4","duration_seconds":1}`), 0644)
	}
	bytes, _ := json.Marshal(run)
	os.WriteFile(filepath.Join(dir, "run.json"), bytes, 0644)
}
func TestViewerIntegration(t *testing.T) {
	root := t.TempDir()
	store, err := artifacts.New(root)
	if err != nil {
		t.Fatal(err)
	}
	server, err := New(store, 0)
	if err != nil {
		t.Fatal(err)
	}
	ts := httptest.NewServer(server.Handler())
	defer ts.Close()
	get := func(p string, headers map[string]string) (int, string, http.Header) {
		req, _ := http.NewRequest("GET", ts.URL+p, nil)
		for k, v := range headers {
			req.Header.Set(k, v)
		}
		response, err := http.DefaultClient.Do(req)
		if err != nil {
			t.Fatal(err)
		}
		defer response.Body.Close()
		b := make([]byte, 1<<20)
		n, _ := response.Body.Read(b)
		return response.StatusCode, string(b[:n]), response.Header
	}
	if code, _, _ := get("/api/runs", nil); code != 200 {
		t.Fatalf("empty API: %d", code)
	}
	live := "20261010T220500Z-abcdef123456"
	battle := "20261010T224000Z-abcdef123456"
	failed := "20261010T230000Z-abcdef123456"
	running := "20261010T231000Z-abcdef123456"
	fixture(t, root, live, "live-capture", "passed", true)
	fixture(t, root, battle, "battle-replay", "passed", true)
	fixture(t, root, failed, "live-capture", "failed", false)
	fixture(t, root, running, "live-capture", "running", true)
	if code, body, _ := get("/", nil); code != 200 || !strings.Contains(body, "Fixture failed") {
		t.Fatalf("dashboard: %d %s", code, body)
	}
	code, body, _ := get("/api/runs?status=passed&type=battle-replay", nil)
	if code != 200 || !strings.Contains(body, battle) || strings.Contains(body, live) {
		t.Fatalf("filter: %d %s", code, body)
	}
	code, body, _ = get("/api/runs?limit=1&offset=0", nil)
	if code != 200 || !strings.Contains(body, running) || strings.Contains(body, failed) {
		t.Fatalf("ordering: %d %s", code, body)
	}
	if code, body, _ := get("/runs/"+failed, nil); code != 200 || !strings.Contains(body, "client-a-final.png") {
		t.Fatalf("failed evidence: %d %s", code, body)
	}
	code, body, headers := get("/media/"+live+"/combined.mp4", map[string]string{"Range": "bytes=3-6"})
	if code != 206 || body != "3456" || headers.Get("Content-Range") != "bytes 3-6/10" || headers.Get("Content-Type") != "video/mp4" {
		t.Fatalf("range: %d %q %v", code, body, headers)
	}
	if code, body, _ := get("/media/"+live+"/combined.mp4", nil); code != 200 || body != "0123456789" {
		t.Fatalf("full video: %d", code)
	}
	if code, _, _ := get("/media/"+running+"/combined.mp4", nil); code != 404 {
		t.Fatalf("incomplete video served: %d", code)
	}
	if code, _, _ := get("/media/"+live+"/run.json", nil); code != 404 {
		t.Fatalf("manifest served: %d", code)
	}
	if code, _, _ := get("/media/"+live+"/%2e%2e%2fcombined.mp4", nil); code != 404 {
		t.Fatalf("traversal served: %d", code)
	}
	os.Symlink(filepath.Join(root, live, "combined.mp4"), filepath.Join(root, failed, "combined.mp4"))
	if code, _, _ := get("/media/"+failed+"/combined.mp4", nil); code != 404 {
		t.Fatalf("unlisted symlink served: %d", code)
	}
	os.Remove(filepath.Join(root, live, "combined.mp4"))
	os.Symlink("/etc/hosts", filepath.Join(root, live, "combined.mp4"))
	if code, _, _ := get("/media/"+live+"/combined.mp4", nil); code != 404 {
		t.Fatalf("symlink escape served: %d", code)
	}
	malformed := "20261010T235000Z-abcdef123456"
	os.Mkdir(filepath.Join(root, malformed), 0755)
	os.WriteFile(filepath.Join(root, malformed, "run.json"), []byte("{"), 0644)
	if code, body, _ := get("/api/runs", nil); code != 200 || strings.Contains(body, malformed) {
		t.Fatalf("malformed manifest: %d %s", code, body)
	}
}
