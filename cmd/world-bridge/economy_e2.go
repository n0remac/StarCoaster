package main

import "errors"

// The logical site and generation come from paired native observations. The
// native controller still checks the exact current BWAPI unit before ordering
// a worker; no resource amount or reward is calculated in the bridge.
func (s *service) prepareGatherCommand(command *worldCommand) error {
	if !s.finiteEconomy() || s.resources == nil || len(command.UnitIDs) != 1 ||
		!s.constructionWorker(command.UnitIDs[0]) {
		return errors.New("worker_unavailable")
	}
	state, ok := s.resources.Latest(command.TargetID)
	if !ok || state.Generation == 0 || state.Generation != command.TargetGeneration ||
		state.ControllerNativeID == "" || state.PublisherNativeID == "" ||
		!((state.Type == "mineral_field" && state.Lifecycle == "deposit" && state.Owner == 11 && state.Amount > 0) ||
			(state.Type == "terran_refinery" && state.Lifecycle == "refinery" && state.Owner == 1 && state.Amount > 0)) {
		return errors.New("stale_resource_target")
	}
	command.TargetNativeID = state.ControllerNativeID
	command.NativeGeneration = state.Generation
	return nil
}
