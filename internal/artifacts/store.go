package artifacts

import (
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strings"
)

var runID = regexp.MustCompile(`^\d{8}T\d{6}Z-[0-9a-f]{12}$`)
var imageName = regexp.MustCompile(`^(client-[ab]-(early|later|final|t[0-9.]+)(-rot[0-3])?|frame-[0-9]+|park-background)\.png$`)
var ErrNotFound = errors.New("artifact not found")

type File struct {
	Path  string `json:"path"`
	Label string `json:"label"`
}
type Run struct {
	SchemaVersion     int            `json:"schema_version"`
	ID                string         `json:"id"`
	Type              string         `json:"type"`
	Title             string         `json:"title"`
	Status            string         `json:"status"`
	StartedAt         string         `json:"started_at"`
	FinishedAt        *string        `json:"finished_at"`
	CommitSHA         string         `json:"commit_sha"`
	Videos            []File         `json:"videos"`
	Screenshots       []File         `json:"screenshots"`
	VerificationFile  *string        `json:"verification_file"`
	VideoMetadataFile *string        `json:"video_metadata_file"`
	ScenarioConfigFile *string        `json:"scenario_config_file,omitempty"`
	Logs              []File         `json:"logs"`
	Error             *string        `json:"error"`
	CaptureConfig     map[string]any `json:"capture_config,omitempty"`
	SizeBytes         int64          `json:"size_bytes"`
}
type Detail struct {
	Run
	Verification  map[string]any    `json:"verification,omitempty"`
	VideoMetadata map[string]any    `json:"video_metadata,omitempty"`
	Events        []map[string]any  `json:"events"`
	LogPreviews   map[string]string `json:"log_previews,omitempty"`
}
type Store struct{ Root string }

func New(root string) (*Store, error) {
	abs, err := filepath.Abs(root)
	if err != nil {
		return nil, err
	}
	if err = os.MkdirAll(abs, 0750); err != nil {
		return nil, err
	}
	abs, err = filepath.EvalSymlinks(abs)
	if err != nil {
		return nil, err
	}
	return &Store{Root: abs}, nil
}
func validRun(r Run, id string) bool {
	if r.SchemaVersion != 1 || r.ID != id || !runID.MatchString(id) ||
		(r.Type != "live-capture" && r.Type != "battle-replay") ||
		(r.Status != "running" && r.Status != "passed" && r.Status != "failed" && r.Status != "interrupted") || r.StartedAt == "" {
		return false
	}
	for _, f := range r.Videos {
		if f.Path != "combined.mp4" && f.Path != "client-a.mp4" && f.Path != "client-b.mp4" {
			return false
		}
	}
	for _, f := range r.Screenshots {
		if !imageName.MatchString(f.Path) {
			return false
		}
	}
	allowedLogs := map[string]bool{"diagnostic-client-a.log": true, "diagnostic-client-b.log": true, "diagnostic-server.log": true, "diagnostic-bwapi.log": true, "diagnostic-bwapi-restart.log": true, "diagnostic-video-capture.log": true}
	for _, f := range r.Logs {
		if !allowedLogs[f.Path] {
			return false
		}
	}
	if r.VerificationFile != nil && *r.VerificationFile != "verification.json" {
		return false
	}
	if r.VideoMetadataFile != nil && *r.VideoMetadataFile != "video-metadata.json" {
		return false
	}
	if r.ScenarioConfigFile != nil && *r.ScenarioConfigFile != "scenario-config.json" {
		return false
	}
	return true
}
func safeName(name string) bool {
	return name != "" && name == filepath.Base(name) && !strings.HasPrefix(name, ".") && !strings.ContainsAny(name, "/\\") && !strings.Contains(name, "..")
}
func regular(path string) bool {
	info, err := os.Lstat(path)
	return err == nil && info.Mode().IsRegular()
}
func (s *Store) directory(id string) (string, error) {
	if !runID.MatchString(id) {
		return "", ErrNotFound
	}
	path := filepath.Join(s.Root, id)
	info, err := os.Lstat(path)
	if err != nil || !info.IsDir() || info.Mode()&os.ModeSymlink != 0 {
		return "", ErrNotFound
	}
	return path, nil
}
func (s *Store) Get(id string) (Run, error) {
	dir, err := s.directory(id)
	if err != nil {
		return Run{}, err
	}
	path := filepath.Join(dir, "run.json")
	if !regular(path) {
		return Run{}, ErrNotFound
	}
	bytes, err := os.ReadFile(path)
	if err != nil || len(bytes) > 2<<20 {
		return Run{}, ErrNotFound
	}
	var r Run
	if json.Unmarshal(bytes, &r) != nil || !validRun(r, id) {
		return Run{}, ErrNotFound
	}
	return r, nil
}
func (s *Store) List(status, kind string, limit, offset int) []Run {
	entries, err := os.ReadDir(s.Root)
	if err != nil {
		return []Run{}
	}
	result := make([]Run, 0)
	for _, entry := range entries {
		if !entry.IsDir() {
			continue
		}
		r, err := s.Get(entry.Name())
		if err == nil && (status == "" || r.Status == status) && (kind == "" || r.Type == kind) {
			result = append(result, r)
		}
	}
	sort.Slice(result, func(i, j int) bool {
		if result[i].StartedAt == result[j].StartedAt {
			return result[i].ID > result[j].ID
		}
		return result[i].StartedAt > result[j].StartedAt
	})
	if offset > len(result) {
		return []Run{}
	}
	result = result[offset:]
	if limit > 0 && limit < len(result) {
		result = result[:limit]
	}
	return result
}
func (s *Store) file(r Run, name string) (string, error) {
	if !safeName(name) {
		return "", ErrNotFound
	}
	dir, err := s.directory(r.ID)
	if err != nil {
		return "", err
	}
	path := filepath.Join(dir, name)
	if !regular(path) {
		return "", ErrNotFound
	}
	return path, nil
}
func (s *Store) Media(r Run, name string) (string, string, error) {
	if r.ScenarioConfigFile != nil && name == *r.ScenarioConfigFile {
		path, err := s.file(r, name)
		return path, "application/json", err
	}
	for _, f := range r.Videos {
		if f.Path == name && filepath.Ext(name) == ".mp4" {
			if r.Status == "running" || !s.validatedVideo(r, name) {
				return "", "", ErrNotFound
			}
			path, err := s.file(r, name)
			return path, "video/mp4", err
		}
	}
	for _, f := range r.Screenshots {
		if f.Path == name && filepath.Ext(name) == ".png" {
			path, err := s.file(r, name)
			return path, "image/png", err
		}
	}
	for _, f := range r.Logs {
		if f.Path == name && strings.HasPrefix(name, "diagnostic-") && filepath.Ext(name) == ".log" {
			path, err := s.file(r, name)
			return path, "text/plain; charset=utf-8", err
		}
	}
	return "", "", ErrNotFound
}

func (s *Store) validatedVideo(r Run, name string) bool {
	metadata := s.readJSON(r, r.VideoMetadataFile)
	if metadata == nil {
		return false
	}
	if metadata["filename"] == name {
		duration, ok := metadata["duration_seconds"].(float64)
		return ok && duration > 0
	}
	outputs, ok := metadata["outputs"].([]any)
	if !ok {
		return false
	}
	for _, value := range outputs {
		output, ok := value.(map[string]any)
		if !ok || output["filename"] != name || output["validation_error"] != nil {
			continue
		}
		duration, ok := output["duration_seconds"].(float64)
		if ok && duration > 0 {
			return true
		}
	}
	return false
}
func (s *Store) readJSON(r Run, name *string) map[string]any {
	if name == nil {
		return nil
	}
	path, err := s.file(r, *name)
	if err != nil {
		return nil
	}
	b, err := os.ReadFile(path)
	if err != nil || len(b) > 2<<20 {
		return nil
	}
	var result map[string]any
	if json.Unmarshal(b, &result) != nil {
		return nil
	}
	return result
}
func (s *Store) Detail(r Run) Detail {
	d := Detail{Run: r, Verification: s.readJSON(r, r.VerificationFile), VideoMetadata: s.readJSON(r, r.VideoMetadataFile), Events: []map[string]any{}, LogPreviews: map[string]string{}}
	if events, ok := d.VideoMetadata["events"].([]any); ok {
		for _, item := range events {
			if event, ok := item.(map[string]any); ok {
				d.Events = append(d.Events, event)
			}
		}
	}
	for _, f := range r.Logs {
		path, _, err := s.Media(r, f.Path)
		if err != nil {
			continue
		}
		file, err := os.Open(path)
		if err != nil {
			continue
		}
		buf := make([]byte, 8192)
		n, _ := file.Read(buf)
		file.Close()
		d.LogPreviews[f.Path] = string(buf[:n])
	}
	return d
}
func (r Run) ShortSHA() string {
	if len(r.CommitSHA) > 8 {
		return r.CommitSHA[:8]
	}
	return r.CommitSHA
}
func (r Run) Description() string {
	if r.Type == "battle-replay" {
		return "OpenBW trace composited over a static OpenRCT2 park capture"
	}
	return "Live OpenRCT2 graphical clients"
}
func (r Run) String() string { return fmt.Sprintf("%s %s", r.ID, r.Status) }
