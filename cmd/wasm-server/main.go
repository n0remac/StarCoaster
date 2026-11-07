// wasm-server serves the browser bundle and forwards one fixed WebSocket
// endpoint to the native OpenRCT2 TCP multiplayer server.
package main

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"log"
	"net"
	"net/http"
	"net/url"
	"os"
	"os/exec"
	"os/signal"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
	"sync/atomic"
	"syscall"
	"time"

	"github.com/gorilla/websocket"
)

type licensedFile struct {
	Path   string `json:"path"`
	Size   int64  `json:"size"`
	SHA256 string `json:"sha256"`
}

type gatewayPerformance struct {
	fromBrowserBytes    atomic.Int64
	toBrowserBytes      atomic.Int64
	fromBrowserMessages atomic.Int64
	toBrowserMessages   atomic.Int64
	writeBlockedNS      atomic.Int64
	connections         atomic.Int64
	disconnections      atomic.Int64
}

func newGatewayPerformance() *gatewayPerformance {
	dir := os.Getenv("STARCOASTER_PERF_DIR")
	if dir == "" {
		return nil
	}
	if err := os.MkdirAll(dir, 0750); err != nil {
		return nil
	}
	file, err := os.OpenFile(filepath.Join(dir, "gateway-network.jsonl"), os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0640)
	if err != nil {
		return nil
	}
	p := &gatewayPerformance{}
	go func() {
		for range time.NewTicker(time.Second).C {
			record := map[string]any{"source": "gateway", "stage": "websocket_second",
				"wall_utc": time.Now().UTC().Format(time.RFC3339Nano),
				"bytes_in": p.fromBrowserBytes.Swap(0), "bytes_out": p.toBrowserBytes.Swap(0),
				"messages_in": p.fromBrowserMessages.Swap(0), "messages_out": p.toBrowserMessages.Swap(0),
				"write_blocked_us": p.writeBlockedNS.Swap(0) / 1000,
				"connections":      p.connections.Load(), "disconnections": p.disconnections.Load()}
			if line, err := json.Marshal(record); err == nil {
				_, _ = file.Write(append(line, '\n'))
			}
		}
	}()
	return p
}

type licensedManifest struct {
	Schema  int            `json:"schema"`
	Version string         `json:"version"`
	Files   []licensedFile `json:"files"`
}

type licensedAssets struct {
	root        string
	manifest    []byte
	files       map[string]struct{}
	cacheHits   int
	hashedFiles int
}

type licensedCacheEntry struct {
	Size    int64  `json:"size"`
	MtimeNS int64  `json:"mtime_ns"`
	CtimeNS int64  `json:"ctime_ns"`
	Device  uint64 `json:"device"`
	Inode   uint64 `json:"inode"`
	SHA256  string `json:"sha256"`
}

type licensedInventoryCache struct {
	Schema int                           `json:"schema"`
	Root   string                        `json:"root"`
	Files  map[string]licensedCacheEntry `json:"files"`
}

func licensedSignature(info os.FileInfo) (licensedCacheEntry, error) {
	stat, ok := info.Sys().(*syscall.Stat_t)
	if !ok {
		return licensedCacheEntry{}, fmt.Errorf("RCT2 file metadata unavailable: %s", info.Name())
	}
	return licensedCacheEntry{Size: info.Size(), MtimeNS: info.ModTime().UnixNano(),
		CtimeNS: stat.Ctim.Nano(), Device: uint64(stat.Dev), Inode: stat.Ino}, nil
}

func readLicensedInventoryCache(path, root string) licensedInventoryCache {
	cache := licensedInventoryCache{Schema: 1, Root: root, Files: map[string]licensedCacheEntry{}}
	if path == "" {
		return cache
	}
	info, err := os.Lstat(path)
	if err != nil || !info.Mode().IsRegular() {
		return cache
	}
	contents, err := os.ReadFile(path)
	if err != nil {
		return cache
	}
	var saved licensedInventoryCache
	if json.Unmarshal(contents, &saved) == nil && saved.Schema == 1 && saved.Root == root && saved.Files != nil {
		return saved
	}
	return cache
}

func writeLicensedInventoryCache(path string, cache licensedInventoryCache) error {
	if path == "" {
		return nil
	}
	if err := os.MkdirAll(filepath.Dir(path), 0750); err != nil {
		return err
	}
	if info, err := os.Lstat(path); err == nil && !info.Mode().IsRegular() {
		return fmt.Errorf("unsafe RCT2 inventory cache: %s", path)
	} else if err != nil && !os.IsNotExist(err) {
		return err
	}
	contents, err := json.Marshal(cache)
	if err != nil {
		return err
	}
	temporary, err := os.CreateTemp(filepath.Dir(path), ".rct2-inventory-*")
	if err != nil {
		return err
	}
	defer os.Remove(temporary.Name())
	if err := temporary.Chmod(0600); err != nil {
		temporary.Close()
		return err
	}
	if _, err := temporary.Write(contents); err != nil {
		temporary.Close()
		return err
	}
	if err := temporary.Close(); err != nil {
		return err
	}
	return os.Rename(temporary.Name(), path)
}

func loadLicensedAssets(root string) (*licensedAssets, error) {
	if root == "" {
		return nil, nil
	}
	resolved, err := filepath.EvalSymlinks(root)
	if err != nil {
		return nil, fmt.Errorf("RCT2 data path: %w", err)
	}
	if info, err := os.Stat(filepath.Join(resolved, "Data", "ch.dat")); err != nil || !info.Mode().IsRegular() {
		return nil, fmt.Errorf("RCT2 data path %s must contain Data/ch.dat", resolved)
	}
	assets := &licensedAssets{root: resolved, files: make(map[string]struct{})}
	entryList := make([]licensedFile, 0, 2500)
	cachePath := os.Getenv("WASM_RCT2_INVENTORY_CACHE")
	cached := readLicensedInventoryCache(cachePath, resolved)
	updated := licensedInventoryCache{Schema: 1, Root: resolved, Files: make(map[string]licensedCacheEntry)}
	err = filepath.WalkDir(resolved, func(path string, entry os.DirEntry, walkErr error) error {
		if walkErr != nil {
			return walkErr
		}
		if entry.IsDir() {
			return nil
		}
		if !entry.Type().IsRegular() {
			return fmt.Errorf("RCT2 data contains an unsupported file: %s", path)
		}
		relative, err := filepath.Rel(resolved, path)
		if err != nil {
			return err
		}
		relative = filepath.ToSlash(relative)
		info, err := entry.Info()
		if err != nil {
			return err
		}
		signature, err := licensedSignature(info)
		if err != nil {
			return err
		}
		previous, found := cached.Files[relative]
		if found && previous.Size == signature.Size && previous.MtimeNS == signature.MtimeNS &&
			previous.CtimeNS == signature.CtimeNS && previous.Device == signature.Device &&
			previous.Inode == signature.Inode && len(previous.SHA256) == 64 {
			if digest, err := hex.DecodeString(previous.SHA256); err == nil && len(digest) == sha256.Size {
				signature.SHA256 = previous.SHA256
				assets.cacheHits++
			}
		}
		if signature.SHA256 == "" {
			file, err := os.Open(path)
			if err != nil {
				return err
			}
			digest := sha256.New()
			size, copyErr := io.Copy(digest, file)
			closeErr := file.Close()
			if copyErr != nil {
				return copyErr
			}
			if closeErr != nil {
				return closeErr
			}
			after, err := os.Stat(path)
			if err != nil {
				return err
			}
			current, err := licensedSignature(after)
			if err != nil {
				return err
			}
			if current.Size != signature.Size || current.MtimeNS != signature.MtimeNS ||
				current.CtimeNS != signature.CtimeNS || current.Device != signature.Device ||
				current.Inode != signature.Inode || size != signature.Size {
				return fmt.Errorf("RCT2 file changed during inventory: %s", path)
			}
			signature.SHA256 = hex.EncodeToString(digest.Sum(nil))
			assets.hashedFiles++
		}
		entryList = append(entryList, licensedFile{Path: relative, Size: signature.Size,
			SHA256: signature.SHA256})
		updated.Files[relative] = signature
		assets.files[relative] = struct{}{}
		return nil
	})
	if err != nil {
		return nil, fmt.Errorf("inventory RCT2 data: %w", err)
	}
	if err := writeLicensedInventoryCache(cachePath, updated); err != nil {
		log.Printf("RCT2 inventory cache unavailable: %v", err)
	}
	sort.Slice(entryList, func(i, j int) bool { return entryList[i].Path < entryList[j].Path })
	version := sha256.New()
	for _, entry := range entryList {
		_, _ = io.WriteString(version, entry.Path+"\x00"+strconv.FormatInt(entry.Size, 10)+"\x00"+entry.SHA256+"\n")
	}
	manifest, err := json.Marshal(licensedManifest{Schema: 1, Version: hex.EncodeToString(version.Sum(nil)), Files: entryList})
	if err != nil {
		return nil, err
	}
	assets.manifest = manifest
	return assets, nil
}

func sameOrigin(r *http.Request) bool {
	origin := r.Header.Get("Origin")
	if origin == "" {
		return false
	}
	parsed, err := url.Parse(origin)
	if err != nil || parsed.Host != r.Host || parsed.User != nil || parsed.RawQuery != "" || parsed.Fragment != "" || parsed.Path != "" {
		return false
	}
	if r.Header.Get("X-Forwarded-Proto") == "https" {
		return parsed.Scheme == "https"
	}
	return parsed.Scheme == "http" || parsed.Scheme == "https"
}

func loopbackAddress(address string) error {
	host, _, err := net.SplitHostPort(address)
	if err != nil {
		return err
	}
	ip := net.ParseIP(host)
	if ip == nil || !ip.IsLoopback() {
		return fmt.Errorf("must use a numeric loopback address: %s", address)
	}
	return nil
}

func funnelTargetsListen(config []byte, listen string) (bool, error) {
	var status struct {
		AllowFunnel map[string]bool `json:"AllowFunnel"`
		Web         map[string]struct {
			Handlers map[string]struct {
				Proxy string `json:"Proxy"`
			} `json:"Handlers"`
		} `json:"Web"`
	}
	if err := json.Unmarshal(config, &status); err != nil {
		return false, err
	}
	listenHost, listenPort, err := net.SplitHostPort(listen)
	if err != nil {
		return false, err
	}
	for endpoint, public := range status.AllowFunnel {
		if !public {
			continue
		}
		for _, handler := range status.Web[endpoint].Handlers {
			target, err := url.Parse(handler.Proxy)
			if err != nil {
				return false, err
			}
			host, port, err := net.SplitHostPort(target.Host)
			if err != nil {
				continue
			}
			if port == listenPort && (host == listenHost || host == "localhost" && listenHost == "127.0.0.1") {
				return true, nil
			}
		}
	}
	return false, nil
}

func checkTailscaleFunnel(listen string) error {
	config, err := exec.Command("tailscale", "serve", "status", "--json").Output()
	if errors.Is(err, exec.ErrNotFound) {
		return nil
	}
	if err != nil {
		return nil
	}
	public, err := funnelTargetsListen(config, listen)
	if err != nil {
		return fmt.Errorf("cannot inspect Tailscale Serve configuration: %w", err)
	}
	if public {
		return fmt.Errorf("refusing to serve private game assets on %s: an active Tailscale Funnel route publicly forwards to this listener", listen)
	}
	return nil
}

func handler(bundle, native string, assets *licensedAssets, supervisorSocket ...string) http.Handler {
	upgrader := websocket.Upgrader{CheckOrigin: sameOrigin, Subprotocols: []string{"binary"}}
	perf := newGatewayPerformance()
	mux := http.NewServeMux()
	if len(supervisorSocket) > 0 && supervisorSocket[0] != "" {
		path := supervisorSocket[0]
		transport := &http.Transport{DialContext: func(ctx context.Context, _, _ string) (net.Conn, error) {
			return (&net.Dialer{Timeout: 2 * time.Second}).DialContext(ctx, "unix", path)
		}}
		client := &http.Client{Transport: transport, Timeout: 5 * time.Minute}
		forward := func(w http.ResponseWriter, r *http.Request, route string) {
			request, err := http.NewRequestWithContext(r.Context(), r.Method, "http://supervisor"+route, r.Body)
			if err != nil {
				http.Error(w, "Invalid session request", http.StatusBadRequest)
				return
			}
			request.ContentLength = r.ContentLength
			if route == "/upload" {
				request.Header.Set("X-StarCoaster-Filename", r.Header.Get("X-StarCoaster-Filename"))
			}
			response, err := client.Do(request)
			if err != nil {
				http.Error(w, "Park session supervisor unavailable", http.StatusServiceUnavailable)
				return
			}
			defer response.Body.Close()
			w.Header().Set("Cache-Control", "private, no-store")
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(response.StatusCode)
			_, _ = io.Copy(w, io.LimitReader(response.Body, 16<<10))
		}
		mux.HandleFunc("/private/park-session", func(w http.ResponseWriter, r *http.Request) {
			if r.Method != http.MethodGet && r.Method != http.MethodHead {
				http.Error(w, "GET required", http.StatusMethodNotAllowed)
				return
			}
			forward(w, r, "/state")
		})
		mux.HandleFunc("/private/park-session/", func(w http.ResponseWriter, r *http.Request) {
			if r.Method != http.MethodPost {
				http.Error(w, "POST required", http.StatusMethodNotAllowed)
				return
			}
			if !sameOrigin(r) {
				http.Error(w, "Origin denied", http.StatusForbidden)
				return
			}
			route := strings.TrimPrefix(r.URL.Path, "/private/park-session")
			if route != "/load" && route != "/cancel" && route != "/title" && route != "/upload" {
				http.NotFound(w, r)
				return
			}
			limit := int64(4096)
			if route == "/upload" {
				limit = 64 << 20
			}
			if r.ContentLength < 1 || r.ContentLength > limit {
				http.Error(w, "Invalid session request size", http.StatusRequestEntityTooLarge)
				return
			}
			forward(w, r, route)
		})
	}
	if assets != nil {
		mux.HandleFunc("/private/rct2/manifest.json", func(w http.ResponseWriter, r *http.Request) {
			if r.Method != http.MethodGet && r.Method != http.MethodHead {
				http.Error(w, "GET required", http.StatusMethodNotAllowed)
				return
			}
			w.Header().Set("Cache-Control", "private, no-store")
			w.Header().Set("Content-Type", "application/json")
			_, _ = w.Write(assets.manifest)
		})
		mux.HandleFunc("/private/rct2/files/", func(w http.ResponseWriter, r *http.Request) {
			if r.Method != http.MethodGet && r.Method != http.MethodHead {
				http.Error(w, "GET required", http.StatusMethodNotAllowed)
				return
			}
			relative := strings.TrimPrefix(r.URL.Path, "/private/rct2/files/")
			if _, allowed := assets.files[relative]; !allowed {
				http.NotFound(w, r)
				return
			}
			w.Header().Set("Cache-Control", "private, no-store")
			w.Header().Set("Content-Type", "application/octet-stream")
			http.ServeFile(w, r, filepath.Join(assets.root, filepath.FromSlash(relative)))
		})
	}
	mux.HandleFunc("/ws", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			http.Error(w, "GET required", http.StatusMethodNotAllowed)
			return
		}
		if !sameOrigin(r) {
			log.Printf("OpenRCT2 gateway rejected WebSocket origin %q for host %q", r.Header.Get("Origin"), r.Host)
			http.Error(w, "Origin denied", http.StatusForbidden)
			return
		}
		tcp, err := net.DialTimeout("tcp", native, 5*time.Second)
		if err != nil {
			log.Printf("OpenRCT2 gateway native connection failed: %v", err)
			http.Error(w, "OpenRCT2 server is unavailable", http.StatusBadGateway)
			return
		}
		defer tcp.Close()
		ws, err := upgrader.Upgrade(w, r, nil)
		if err != nil {
			log.Printf("WebSocket upgrade: %v", err)
			return
		}
		defer ws.Close()
		if perf != nil {
			perf.connections.Add(1)
			defer perf.disconnections.Add(1)
		}
		log.Printf("OpenRCT2 gateway connected")
		ws.SetReadLimit(64 << 20)
		done := make(chan error, 2)
		go func() {
			for {
				kind, reader, err := ws.NextReader()
				if err != nil {
					done <- err
					return
				}
				if kind != websocket.BinaryMessage {
					done <- errors.New("non-binary multiplayer frame")
					return
				}
				count, copyErr := io.Copy(tcp, reader)
				if perf != nil {
					perf.fromBrowserBytes.Add(count)
					perf.fromBrowserMessages.Add(1)
				}
				if err = copyErr; err != nil {
					done <- err
					return
				}
			}
		}()
		go func() {
			buffer := make([]byte, 32<<10)
			for {
				count, err := tcp.Read(buffer)
				if count > 0 {
					writeStart := time.Now()
					if writeErr := ws.WriteMessage(websocket.BinaryMessage, buffer[:count]); writeErr != nil {
						done <- writeErr
						return
					}
					if perf != nil {
						perf.toBrowserBytes.Add(int64(count))
						perf.toBrowserMessages.Add(1)
						perf.writeBlockedNS.Add(time.Since(writeStart).Nanoseconds())
					}
				}
				if err != nil {
					done <- err
					return
				}
			}
		}()
		err = <-done
		if err != nil && !errors.Is(err, io.EOF) && !websocket.IsCloseError(err, websocket.CloseNormalClosure, websocket.CloseGoingAway) {
			log.Printf("OpenRCT2 gateway disconnected: %v", err)
		} else {
			log.Printf("OpenRCT2 gateway closed: %v", err)
		}
	})
	files := http.FileServer(http.Dir(bundle))
	mux.Handle("/", files)
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Cross-Origin-Opener-Policy", "same-origin")
		w.Header().Set("Cross-Origin-Embedder-Policy", "require-corp")
		w.Header().Set("Cross-Origin-Resource-Policy", "same-origin")
		w.Header().Set("X-Content-Type-Options", "nosniff")
		switch r.URL.Path {
		case "/", "/index.html", "/index.js", "/manifest.json":
			w.Header().Set("Cache-Control", "no-store")
		}
		// The manifest changes with each local bundle, while OpenRCT2's
		// generated script and WASM keep stable filenames. A cached script
		// paired with a new WASM can lose exported bridge functions.
		if extension := filepath.Ext(r.URL.Path); extension == ".js" || extension == ".wasm" {
			w.Header().Set("Cache-Control", "no-store")
		}
		if filepath.Ext(r.URL.Path) == ".wasm" {
			w.Header().Set("Content-Type", "application/wasm")
		}
		mux.ServeHTTP(w, r)
	})
}

func main() {
	bundle := flag.String("bundle", "build/wasm-client", "private browser bundle directory")
	listen := flag.String("listen", "127.0.0.1:8091", "loopback HTTP listen address")
	native := flag.String("native", "127.0.0.1:11753", "loopback native OpenRCT2 server address")
	rct2Data := flag.String("rct2-data-path", "", "private licensed RCT2 installation to provision to this browser origin")
	supervisorSocket := flag.String("supervisor-socket", "", "private Unix socket for park transition status")
	flag.Parse()
	for _, address := range []string{*listen, *native} {
		if err := loopbackAddress(address); err != nil {
			log.Fatal(err)
		}
	}
	if err := checkTailscaleFunnel(*listen); err != nil {
		log.Fatal(err)
	}
	if _, err := os.Stat(filepath.Join(*bundle, "manifest.json")); err != nil {
		log.Fatalf("bundle unavailable: %v", err)
	}
	assets, err := loadLicensedAssets(*rct2Data)
	if err != nil {
		log.Fatal(err)
	}
	if assets != nil {
		log.Printf("private RCT2 provisioning enabled: %d licensed files", len(assets.files))
	}
	server := &http.Server{Addr: *listen, Handler: handler(*bundle, *native, assets, *supervisorSocket), ReadHeaderTimeout: 10 * time.Second}
	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()
	go func() {
		<-ctx.Done()
		shutdown, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		_ = server.Shutdown(shutdown)
	}()
	log.Printf("StarCoaster browser server listening on %s, forwarding /ws to %s", *listen, *native)
	if err := server.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
		log.Fatal(err)
	}
}
