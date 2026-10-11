package viewer

import (
	"encoding/json"
	"fmt"
	"html/template"
	"io"
	"net/http"
	"os"
	"path"
	"strconv"
	"strings"
	"time"

	"starcoaster/internal/artifacts"
	"starcoaster/web"
)

type Server struct {
	Store     *artifacts.Store
	MaxRuns   int
	templates *template.Template
}

func New(store *artifacts.Store, maxRuns int) (*Server, error) {
	funcs := template.FuncMap{
		"short": func(s string) string {
			if len(s) > 8 {
				return s[:8]
			}
			return s
		},
		"duration": duration,
		"clock": func(s string) string {
			t, e := time.Parse(time.RFC3339Nano, s)
			if e != nil {
				return s
			}
			return t.Format("Jan 2, 2006 15:04 UTC")
		},
		"seek": seek,
		"shotTime": func(name string, events []map[string]any) string {
			for _, event := range events {
				if event["filename"] == name {
					if seconds, ok := event["scheduled_seconds"].(float64); ok {
						return fmt.Sprintf(" · %.1f s", seconds)
					}
				}
			}
			return ""
		},
		"json": func(v any) string { b, _ := json.MarshalIndent(v, "", "  "); return string(b) },
	}
	t, err := template.New("").Funcs(funcs).ParseFS(web.Assets, "templates/*.html")
	return &Server{Store: store, MaxRuns: maxRuns, templates: t}, err
}
func duration(v map[string]any) string {
	if v == nil {
		return ""
	}
	if outputs, ok := v["outputs"].([]any); ok && len(outputs) > 0 {
		if first, ok := outputs[0].(map[string]any); ok {
			v = first
		}
	}
	if seconds, ok := v["duration_seconds"].(float64); ok {
		return fmt.Sprintf("%.1f s", seconds)
	}
	return ""
}
func seek(event map[string]any, metadata map[string]any) float64 {
	seconds, _ := event["seconds_from_recording_start"].(float64)
	if outputs, ok := metadata["outputs"].([]any); ok && len(outputs) > 0 {
		if first, ok := outputs[0].(map[string]any); ok {
			offset, _ := first["video_start_offset_seconds_estimate"].(float64)
			seconds -= offset
		}
	}
	if seconds < 0 {
		return 0
	}
	return seconds
}
func (s *Server) Handler() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("GET /healthz", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/plain; charset=utf-8")
		io.WriteString(w, "ok\n")
	})
	mux.HandleFunc("GET /static/", func(w http.ResponseWriter, r *http.Request) {
		name := strings.TrimPrefix(r.URL.Path, "/")
		if name != "static/style.css" && name != "static/viewer.js" {
			http.NotFound(w, r)
			return
		}
		b, err := web.Assets.ReadFile(name)
		if err != nil {
			http.NotFound(w, r)
			return
		}
		if strings.HasSuffix(name, ".css") {
			w.Header().Set("Content-Type", "text/css; charset=utf-8")
		} else {
			w.Header().Set("Content-Type", "text/javascript; charset=utf-8")
		}
		w.Write(b)
	})
	mux.HandleFunc("GET /", s.dashboard)
	mux.HandleFunc("GET /runs/{id}", s.runPage)
	mux.HandleFunc("GET /api/runs", s.apiRuns)
	mux.HandleFunc("GET /api/runs/{id}", s.apiRun)
	mux.HandleFunc("GET /media/{id}/{filename}", s.media)
	return mux
}
func (s *Server) pagination(r *http.Request) (int, int, bool) {
	limit, offset := 50, 0
	if raw := r.URL.Query().Get("limit"); raw != "" {
		var err error
		limit, err = strconv.Atoi(raw)
		if err != nil || limit < 1 || limit > 200 {
			return 0, 0, false
		}
	}
	if raw := r.URL.Query().Get("offset"); raw != "" {
		var err error
		offset, err = strconv.Atoi(raw)
		if err != nil || offset < 0 {
			return 0, 0, false
		}
	}
	if s.MaxRuns > 0 && limit > s.MaxRuns {
		limit = s.MaxRuns
	}
	return limit, offset, true
}
func (s *Server) query(r *http.Request) ([]artifacts.Run, bool) {
	limit, offset, ok := s.pagination(r)
	if !ok {
		return nil, false
	}
	status, kind := r.URL.Query().Get("status"), r.URL.Query().Get("type")
	if status != "" && status != "running" && status != "passed" && status != "failed" && status != "interrupted" {
		return nil, false
	}
	if kind != "" && kind != "live-capture" && kind != "battle-replay" {
		return nil, false
	}
	return s.Store.List(status, kind, limit, offset), true
}
func jsonReply(w http.ResponseWriter, value any) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	json.NewEncoder(w).Encode(value)
}
func (s *Server) apiRuns(w http.ResponseWriter, r *http.Request) {
	runs, ok := s.query(r)
	if !ok {
		http.Error(w, "invalid query", 400)
		return
	}
	jsonReply(w, runs)
}
func (s *Server) apiRun(w http.ResponseWriter, r *http.Request) {
	run, err := s.Store.Get(r.PathValue("id"))
	if err != nil {
		http.NotFound(w, r)
		return
	}
	jsonReply(w, s.Store.Detail(run))
}
func (s *Server) dashboard(w http.ResponseWriter, r *http.Request) {
	if r.URL.Path != "/" {
		http.NotFound(w, r)
		return
	}
	runs, ok := s.query(r)
	if !ok {
		http.Error(w, "invalid query", 400)
		return
	}
	type card struct {
		artifacts.Run
		Duration string
	}
	cards := make([]card, 0, len(runs))
	for _, run := range runs {
		cards = append(cards, card{run, duration(s.Store.Detail(run).VideoMetadata)})
	}
	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	s.templates.ExecuteTemplate(w, "dashboard.html", map[string]any{"Runs": cards, "Status": r.URL.Query().Get("status"), "Type": r.URL.Query().Get("type")})
}
func (s *Server) runPage(w http.ResponseWriter, r *http.Request) {
	run, err := s.Store.Get(r.PathValue("id"))
	if err != nil {
		http.NotFound(w, r)
		return
	}
	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	s.templates.ExecuteTemplate(w, "run.html", map[string]any{"Detail": s.Store.Detail(run)})
}
func (s *Server) media(w http.ResponseWriter, r *http.Request) {
	run, err := s.Store.Get(r.PathValue("id"))
	if err != nil {
		http.NotFound(w, r)
		return
	}
	name := r.PathValue("filename")
	if name != path.Base(name) {
		http.NotFound(w, r)
		return
	}
	_, mime, err := s.Store.Media(run, name)
	if err != nil {
		http.NotFound(w, r)
		return
	}
	root, err := os.OpenRoot(s.Store.Root)
	if err != nil {
		http.NotFound(w, r)
		return
	}
	defer root.Close()
	f, err := root.Open(path.Join(run.ID, name))
	if err != nil {
		http.NotFound(w, r)
		return
	}
	defer f.Close()
	stat, err := f.Stat()
	if err != nil {
		http.NotFound(w, r)
		return
	}
	w.Header().Set("Content-Type", mime)
	w.Header().Set("X-Content-Type-Options", "nosniff")
	if strings.HasPrefix(mime, "text/plain") {
		w.Header().Set("Content-Disposition", "inline")
		io.Copy(w, io.LimitReader(f, 65536))
		return
	}
	http.ServeContent(w, r, name, stat.ModTime(), f)
}
