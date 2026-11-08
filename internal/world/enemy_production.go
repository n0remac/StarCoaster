package world

import "fmt"

// EnemyProduction is a finite, versioned intent journal. An unresolved train
// order is never replayed: the native publisher must report its cached receipt
// after a bridge reconnect, or production stops as uncertain.
type EnemyProduction struct {
	Version   int                    `json:"version"`
	MaxOrders int                    `json:"max_orders"`
	Orders    []EnemyProductionOrder `json:"orders"`
}

type EnemyProductionOrder struct {
	Sequence         int    `json:"sequence"`
	RequestID        string `json:"request_id"`
	State            string `json:"state"`
	HatcheryNativeID int    `json:"hatchery_native_id"`
	IntentFrame      int    `json:"intent_frame"`
	ResultFrame      int    `json:"result_frame,omitempty"`
	MineralsBefore   int    `json:"minerals_before,omitempty"`
	MineralsAfter    int    `json:"minerals_after,omitempty"`
	Reason           string `json:"reason,omitempty"`
}

func NewEnemyProduction(maxOrders int) *EnemyProduction {
	return &EnemyProduction{Version: 1, MaxOrders: maxOrders, Orders: []EnemyProductionOrder{}}
}

func (p *EnemyProduction) Plan(session string, frame, hatchery int) (EnemyProductionOrder, bool) {
	if p == nil || session == "" || frame < 1 || hatchery < 1 ||
		len(p.Orders) >= p.MaxOrders || p.MaxOrders < 1 || p.MaxOrders > 12 {
		return EnemyProductionOrder{}, false
	}
	for _, order := range p.Orders {
		if order.State != "accepted" {
			return EnemyProductionOrder{}, false
		}
	}
	n := len(p.Orders) + 1
	order := EnemyProductionOrder{Sequence: n, RequestID: fmt.Sprintf("enemy-train:%s:%d", session, n),
		State: "pending", HatcheryNativeID: hatchery, IntentFrame: frame}
	p.Orders = append(p.Orders, order)
	return order, true
}

func (p *EnemyProduction) Pending() *EnemyProductionOrder {
	if p == nil || len(p.Orders) == 0 {
		return nil
	}
	last := &p.Orders[len(p.Orders)-1]
	if last.State == "pending" {
		return last
	}
	return nil
}

func (p *EnemyProduction) Resolve(requestID string, accepted bool, reason string,
	frame, before, after int) bool {
	order := p.Pending()
	if order == nil || order.RequestID != requestID || frame < order.IntentFrame ||
		before < 0 || after < 0 || accepted && after >= before {
		return false
	}
	if accepted {
		order.State = "accepted"
	} else {
		order.State = "rejected"
	}
	order.Reason, order.ResultFrame = reason, frame
	order.MineralsBefore, order.MineralsAfter = before, after
	return true
}

func (p *EnemyProduction) MarkUncertain(requestID string) bool {
	order := p.Pending()
	if order == nil || order.RequestID != requestID {
		return false
	}
	order.State, order.Reason = "uncertain", "native_receipt_missing"
	return true
}

func (p *EnemyProduction) Validate(session string, maxOrders int) error {
	if p == nil || p.Version != 1 || p.MaxOrders != maxOrders ||
		maxOrders < 1 || maxOrders > 12 || len(p.Orders) > maxOrders {
		return fmt.Errorf("enemy_production_journal_invalid")
	}
	for i, order := range p.Orders {
		if order.Sequence != i+1 || order.RequestID != fmt.Sprintf("enemy-train:%s:%d", session, i+1) ||
			order.HatcheryNativeID < 1 || order.IntentFrame < 1 ||
			(order.State != "pending" && order.State != "accepted" && order.State != "rejected" && order.State != "uncertain") ||
			(i < len(p.Orders)-1 && order.State != "accepted") {
			return fmt.Errorf("enemy_production_journal_invalid")
		}
		if order.State == "accepted" && (order.ResultFrame < order.IntentFrame ||
			order.MineralsBefore-order.MineralsAfter != 50) {
			return fmt.Errorf("enemy_production_spend_invalid")
		}
		if order.State == "pending" && order.ResultFrame != 0 {
			return fmt.Errorf("enemy_production_pending_result_invalid")
		}
	}
	return nil
}
