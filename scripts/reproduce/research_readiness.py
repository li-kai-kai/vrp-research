"""Reproduce fairness readiness diagnostics without changing objectives or policy."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.reproduce.benchmark_suite import benchmark_specs, build_benchmark_instance
from scripts.reproduce.capacity_recovery import evaluate_capacity_solution_detailed
from scripts.reproduce.mechanism_applicability import fixed_decisions
from scripts.reproduce.objective_precision import V2_PRECISION
from scripts.reproduce.replay_solutions import _replay_solution
from scripts.reproduce.service_diagnostics import service_rows
from scripts.reproduce.solution_io import (
    RunStore, decision_from_json, decision_hash, decision_to_json, code_environment,
    source_hashes, write_csv_atomic, write_json_atomic,
)


def diagnose(historical_root, search_root, output_dir):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    summaries, periods, demands, zero = [], [], [], []
    inputs, limitations, decisions = {}, [], {}

    def add(instance, decision, identity):
        identity = {**identity, 'decision_hash': decision_hash(decision)}
        decisions[decision_hash(decision)] = decision_to_json(decision)
        outcome = evaluate_capacity_solution_detailed(instance, decision)
        p, d, z = service_rows(instance, decision, identity, path_diagnostics=True)
        summaries.append({**identity, **{f'F{j+1}': v for j, v in enumerate(outcome.objectives)},
                          'F3_key': V2_PRECISION.key(outcome.objectives)[2],
                          'min_satisfaction': outcome.metrics['final_min_satisfaction'],
                          'total_satisfaction': outcome.metrics['final_total_satisfaction'],
                          'zero_service_ratio': outcome.metrics['zero_service_ratio'],
                          'remaining_supply': outcome.metrics['remaining_supply'],
                          'cumulative_min_service_shortfall_hours': sum((1-r['min_satisfaction']) * instance.base.eta_hours for r in p)})
        periods.extend(p)
        demands.extend(d)
        zero.extend(z)

    for cohort, root, case in [('historical_S025', historical_root, 'S025'), ('new_WEN38_search', search_root, 'WEN38')]:
        root = Path(root)
        if not (root / 'runs').is_dir():
            limitations.append(f'Missing {cohort} input: {root}; no historical results fabricated.')
            continue
        store = RunStore(root)
        records = [r for r in store.load_all_runs() if r['case_id'] == case]
        if not records:
            limitations.append(f'No {case} records under {root}')
        for record in records:
            inputs[str(store.run_path(record['run_key']).resolve())] = record['record_sha256']
            instance = store.load_instance(record['instance_file'])
            snapshot = store.instance_path(record['instance_file'])
            inputs[str(snapshot.resolve())] = hashlib.sha256(snapshot.read_bytes()).hexdigest()
            if instance.evaluation.model_version != 'v2' or record['objective_precision'] != V2_PRECISION.as_dict():
                raise ValueError('readiness requires v2 precision')
            for solution in record['pareto_front']:
                saved = _replay_solution(record=record, solution=solution, execution_instance=instance,
                                         execution_model='saved', abs_tolerance=1e-8, rel_tolerance=1e-8)
                if not saved['replay_success']:
                    raise ValueError('readiness planning replay failed')
                add(instance, decision_from_json(solution['decision'], instance),
                    {'cohort': cohort, 'run_key': record['run_key'], 'solution_id': solution['solution_id'],
                     'is_representative': solution['decision_hash'] == record['decision_hash']})
    spec = next(s for s in benchmark_specs('benchmark') if s.case_id == 'WEN38')
    instance = build_benchmark_instance(spec, instance_seed=1, model_version='v2')
    store = RunStore(output_dir / 'fixed_inputs')
    instance_file = store.save_instance(instance)
    for name, decision in fixed_decisions(instance, random_decisions=19, seed=1).items():
        add(instance, decision, {'cohort': 'fixed_WEN38', 'run_key': name, 'solution_id': name, 'is_representative': False})
    for name, rows in [('fairness_decisions', summaries), ('service_periods', periods),
                       ('service_demand_periods', demands), ('zero_service_classification', zero)]:
        write_csv_atomic(output_dir / f'{name}.csv', rows, list(dict.fromkeys(k for r in rows for k in r)))
    write_json_atomic(output_dir / 'decisions.json', decisions)
    cohorts = defaultdict(list)
    for row in summaries:
        cohorts[row['cohort']].append(row)
    manifest = {'environment': code_environment(), 'input_record_hashes': inputs,
                'fixed_instance_file': str(store.instance_path(instance_file).resolve()),
                'fixed_seed': 1, 'fixed_random_decisions': 19,
                'cohorts': {name: {'decisions': len(rows), 'F3_keys': len({r['F3_key'] for r in rows}),
                                     'min_satisfaction_range': [min(r['min_satisfaction'] for r in rows), max(r['min_satisfaction'] for r in rows)]}
                            for name, rows in cohorts.items()},
                'zero_service_reasons': {name: dict(Counter(r['reason'] for r in zero if r['cohort'] == name)) for name in cohorts},
                'limitations': limitations, 'path_scope': 'Topology and one-way within-period travel only; excludes residual edge capacity and vehicle trip quotas.',
                'auxiliary_metric': 'cumulative minimum-service shortfall hours does not replace F3',
                'source_hashes': source_hashes(Path(__file__).resolve().parents[2],
                    [str(p.relative_to(Path(__file__).resolve().parents[2])) for p in Path(__file__).resolve().parent.glob('*.py')])}
    write_json_atomic(output_dir / 'readiness_manifest.json', manifest)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--historical-root', required=True)
    parser.add_argument('--search-root', required=True)
    parser.add_argument('--output-dir', required=True)
    args = parser.parse_args()
    print(json.dumps(diagnose(args.historical_root, args.search_root, args.output_dir)['cohorts'], indent=2))


if __name__ == '__main__':
    main()
