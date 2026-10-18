// wasm-server serves the browser bundle and forwards one fixed WebSocket
// endpoint to the native OpenRCT2 TCP multiplayer server.
package main

import (
	"context"
	"errors"
	"flag"
	"fmt"
	"io"
	"log"
	"net"
	"net/http"
	"net/url"
	"os"
	"os/signal"
	"path/filepath"
	"syscall"
	"time"

	"github.com/gorilla/websocket"
)

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

func handler(bundle, native string) http.Handler {
	upgrader := websocket.Upgrader{CheckOrigin: sameOrigin, Subprotocols: []string{"binary"}}
	mux := http.NewServeMux()
	mux.HandleFunc("/ws", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			http.Error(w, "GET required", http.StatusMethodNotAllowed)
			return
		}
		if !sameOrigin(r) {
			http.Error(w, "Origin denied", http.StatusForbidden)
			return
		}
		tcp, err := net.DialTimeout("tcp", native, 5*time.Second)
		if err != nil {
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
				if _, err = io.Copy(tcp, reader); err != nil {
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
					if writeErr := ws.WriteMessage(websocket.BinaryMessage, buffer[:count]); writeErr != nil {
						done <- writeErr
						return
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
		}
	})
	files := http.FileServer(http.Dir(bundle))
	mux.Handle("/", files)
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Cross-Origin-Opener-Policy", "same-origin")
		w.Header().Set("Cross-Origin-Embedder-Policy", "require-corp")
		w.Header().Set("Cross-Origin-Resource-Policy", "same-origin")
		w.Header().Set("X-Content-Type-Options", "nosniff")
		if filepath.Ext(r.URL.Path) == ".wasm" {
			w.Header().Set("Content-Type", "application/wasm")
		}
		mux.ServeHTTP(w, r)
	})
}

func main() {
	bundle := flag.String("bundle", "build/wasm-client", "private browser bundle directory")
	listen := flag.String("listen", "127.0.0.1:8080", "loopback HTTP listen address")
	native := flag.String("native", "127.0.0.1:11753", "loopback native OpenRCT2 server address")
	flag.Parse()
	for _, address := range []string{*listen, *native} {
		if err := loopbackAddress(address); err != nil {
			log.Fatal(err)
		}
	}
	if _, err := os.Stat(filepath.Join(*bundle, "manifest.json")); err != nil {
		log.Fatalf("bundle unavailable: %v", err)
	}
	server := &http.Server{Addr: *listen, Handler: handler(*bundle, *native), ReadHeaderTimeout: 10 * time.Second}
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
