"""Audited service traces; path availability excludes capacity and trip quotas."""
from __future__ import annotations

import math

from scripts.reproduce.capacity_recovery import _shortest_paths_for_vehicle
from scripts.reproduce.mechanism_applicability import period_trace, assert_matches_evaluator


def service_rows(instance, decision, identity, *, path_diagnostics=False):
    trace = period_trace(instance, decision)
    assert_matches_evaluator(instance, decision, trace)
    base = instance.base
    stock = dict(base.supply_amounts)
    cumulative = {d: 0.0 for d in base.demands}
    first_service = {}
    first_path = {}
    periods, demands = [], []
    for snap in trace.snapshots:
        if path_diagnostics:
            feasible = {d: set() for d in base.demands}
            for vehicle in instance.vehicles:
                for (s, d), (minutes, _) in _shortest_paths_for_vehicle(instance, snap.progress, vehicle).items():
                    if minutes <= base.eta_minutes + 1e-9:
                        feasible[d].add(s)
            for d, suppliers in feasible.items():
                if suppliers and d not in first_path:
                    first_path[d] = (snap.period, sum(stock.values()),
                                     any(stock[s] > 1e-9 for s in suppliers))
        before = sum(stock.values())
        for allocation in snap.allocations:
            stock[allocation["supplier"]] -= allocation["amount"]
        if any(v < -1e-7 for v in stock.values()):
            raise ValueError("negative supplier inventory")
        if not math.isclose(before - sum(stock.values()), snap.delivered_total, abs_tol=1e-7):
            raise ValueError("period material conservation failed")
        for d in base.demands:
            amount = snap.delivered_by_demand.get(d, 0.0)
            cumulative[d] += amount
            if cumulative[d] > 1e-9:
                first_service.setdefault(d, snap.period)
            demands.append({**identity, "period": snap.period, "demand": d,
                            "delivered": amount, "cumulative_delivered": cumulative[d],
                            "satisfaction": min(1.0, cumulative[d] / base.demand_amounts[d])})
        rates = [min(1.0, cumulative[d] / base.demand_amounts[d]) for d in base.demands]
        periods.append({**identity, "period": snap.period, "end_hours": snap.period * base.eta_hours,
                        "total_satisfaction": sum(cumulative.values()) / base.total_demand,
                        "min_satisfaction": min(rates),
                        "zero_service_ratio": sum(v <= 1e-9 for v in cumulative.values()) / len(rates),
                        "remaining_supply": sum(stock.values()),
                        **{f"remaining_supply_{s}": v for s, v in stock.items()}})
    if not math.isclose(sum(stock.values()) + sum(cumulative.values()), sum(base.supply_amounts.values()), abs_tol=1e-7):
        raise ValueError("horizon material conservation failed")
    if not math.isclose(sum(stock.values()), trace.remaining_supply, abs_tol=1e-7):
        raise ValueError("trace inventory differs from shared dispatcher")
    for row in demands:
        row["first_service_period"] = first_service.get(row["demand"])
        if path_diagnostics:
            first, supply, feasible_stock = first_path.get(row["demand"], (None, None, False))
            row.update(first_topology_time_period=first,
                       global_supply_at_first_path=supply,
                       stocked_feasible_supplier_at_period_start=feasible_stock)
    zero_rows = []
    if path_diagnostics:
        for d in base.demands:
            if cumulative[d] > 1e-9:
                continue
            first, supply, feasible_stock = first_path.get(d, (None, None, False))
            reason = ("no_topology_time_path" if first is None else
                      "global_stock_exhausted" if supply <= 1e-9 else
                      "no_stocked_feasible_supplier" if not feasible_stock else
                      "needs_quota_capacity_priority_diagnosis")
            zero_rows.append({**identity, "demand": d, "first_topology_time_period": first,
                              "global_supply_at_first_path": supply,
                              "stocked_feasible_supplier_at_period_start": feasible_stock,
                              "reason": reason})
    return periods, demands, zero_rows
