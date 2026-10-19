package main

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"io"
	"net"
	"net/http"
	"regexp"
	"time"

	"starcoaster/internal/world"
)

type parkSessionState struct {
	Phase      string   `json:"phase"`
	Current    string   `json:"current"`
	Generation string   `json:"generation"`
	Pending    string   `json:"pending"`
	Error      string   `json:"error"`
	Parks      []string `json:"parks"`
}

type parkLoadRequest struct {
	Park        string `json:"park"`
	Decision    string `json:"decision"`
	Generation  string `json:"generation"`
	SaveName    string `json:"save_name,omitempty"`
	PlayerID    int    `json:"player_id"`
	CommanderID int    `json:"commander_id"`
}

type parkLoadStatus struct {
	Accepted   bool   `json:"accepted"`
	Reason     string `json:"reason"`
	Park       string `json:"park"`
	Generation string `json:"generation"`
}

var saveNamePattern = regexp.MustCompile(`^starcoaster-switch-[0-9a-f]{16}\.park$`)

func (s *service) supervisorRequest(method, route string, body any) (parkSessionState, error) {
	if s.parkSupervisorSocket == "" {
		return parkSessionState{}, errors.New("park_switching_unavailable")
	}
	var content io.Reader
	if body != nil {
		data, err := json.Marshal(body)
		if err != nil {
			return parkSessionState{}, err
		}
		content = bytes.NewReader(data)
	}
	request, err := http.NewRequest(method, "http://supervisor"+route, content)
	if err != nil {
		return parkSessionState{}, err
	}
	if body != nil {
		request.Header.Set("Content-Type", "application/json")
	}
	transport := &http.Transport{DialContext: func(ctx context.Context, _, _ string) (net.Conn, error) {
		return (&net.Dialer{Timeout: 2 * time.Second}).DialContext(ctx, "unix", s.parkSupervisorSocket)
	}}
	defer transport.CloseIdleConnections()
	client := &http.Client{Transport: transport, Timeout: 4 * time.Second}
	response, err := client.Do(request)
	if err != nil {
		return parkSessionState{}, errors.New("park_supervisor_unavailable")
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusOK && response.StatusCode != http.StatusAccepted {
		var failure struct {
			Error string `json:"error"`
		}
		_ = json.NewDecoder(io.LimitReader(response.Body, 4096)).Decode(&failure)
		if failure.Error == "" {
			failure.Error = "park_supervisor_rejected"
		}
		return parkSessionState{}, errors.New(failure.Error)
	}
	var state parkSessionState
	if err := json.NewDecoder(io.LimitReader(response.Body, 16<<10)).Decode(&state); err != nil {
		return parkSessionState{}, errors.New("invalid_park_supervisor_status")
	}
	return state, nil
}

func (s *service) parkCatalogRequest(p *peer, m world.Envelope) {
	if m.Session != s.registry.Session || m.Revision != s.registry.Revision || s.parkSupervisorSocket == "" {
		s.ack(p, m, false, "stale_or_unavailable_park_session")
		return
	}
	state, err := s.supervisorRequest(http.MethodGet, "/state", nil)
	if err != nil {
		s.ack(p, m, false, err.Error())
		return
	}
	s.ack(p, m, true, "")
	_ = s.emit(p, "park.catalog", s.registry.Session, s.registry.Revision, state)
}

func (s *service) parkLoad(p *peer, m world.Envelope) {
	var request parkLoadRequest
	var err error
	if m.Decode(&request) != nil || request.PlayerID < 0 || request.PlayerID != request.CommanderID ||
		request.Park == "" || len(request.Park) > 128 ||
		(request.Decision != "save" && request.Decision != "discard") ||
		(request.Decision == "save" && !saveNamePattern.MatchString(request.SaveName)) ||
		(request.Decision == "discard" && request.SaveName != "") {
		err = errors.New("invalid_or_unauthorized_park_load")
	} else if m.Session != s.registry.Session || m.Revision != s.registry.Revision ||
		!s.ready || s.bw == nil || s.controller == nil || s.parkSupervisorSocket == "" ||
		request.Generation != s.parkGeneration {
		err = errors.New("stale_or_unavailable_park_session")
	} else {
		_, err = s.supervisorRequest(http.MethodPost, "/load", request)
	}
	s.ack(p, m, true, "")
	reason := ""
	if err != nil {
		reason = err.Error()
	}
	_ = s.emit(p, "park.load.status", s.registry.Session, s.registry.Revision,
		parkLoadStatus{Accepted: err == nil, Reason: reason, Park: request.Park,
			Generation: s.parkGeneration})
}
