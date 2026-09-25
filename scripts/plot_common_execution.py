"""Plot measured paired effects and stepwise representative service."""
from __future__ import annotations

import argparse
import csv
import hashlib
import sys
from pathlib import Path

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

from scripts.reproduce.solution_io import write_json_atomic

COLORS = {'Full': '#222222', 'No-PR': '#c44e52', 'No-HT': '#4c72b0', 'No-EC': '#55a868'}
STYLES = {'Full': '-', 'No-PR': '--', 'No-HT': '-.', 'No-EC': ':'}
MARKERS = {'Full': 'o', 'No-PR': 's', 'No-HT': '^', 'No-EC': 'x'}


def plot(input_dir, output_dir):
    input_dir, output_dir = Path(input_dir), Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    files = ['execution_pairs.csv', 'representative_periods.csv']
    tables = {}
    for name in files:
        with (input_dir / name).open() as stream:
            tables[name] = list(csv.DictReader(stream))
    pairs = tables[files[0]]
    group = lambda r: (r['case_id'], r['zone'], r['instance_seed'])
    groups = sorted({group(r) for r in pairs})
    fig, axes = plt.subplots(1, 2, figsize=(12, 5), sharey=True, layout='constrained')
    for ax, metric, label in zip(axes, ['delta_hv', 'delta_igd'], ['HV(Full) - HV(simplified)', 'IGD(simplified) - IGD(Full)']):
        for row in pairs:
            model = row['model']
            # Deterministic offsets expose each paired solver repeat; no aggregation.
            offset = {'No-PR': -.22, 'No-HT': 0, 'No-EC': .22}[model]
            offset += (int(row['solver_repeat']) - .5) * .075
            ax.scatter(float(row[metric]), groups.index(group(row)) + offset,
                       color=COLORS[model], marker=MARKERS[model], s=38, alpha=.85)
        ax.axvline(0, color='#888888', linewidth=.8)
        ax.set_xlabel(label + '\nPositive values favor Full')
        ax.grid(axis='x', alpha=.15)
        ax.set_yticks(range(len(groups)), [f'{c} / {z} / i{s}' for c, z, s in groups])
        ax.invert_yaxis()
    axes[1].legend(handles=[Line2D([], [], linestyle='', marker=MARKERS[m], color=COLORS[m], label=m) for m in ['No-PR', 'No-HT', 'No-EC']], loc='best')
    fig.suptitle('Common Full execution: each point is one paired solver run\nReferences and normalization are separate for each physical configuration', fontsize=12)
    for suffix in ['png', 'pdf']:
        fig.savefig(output_dir / f'paired_execution_advantages.{suffix}', dpi=180)
    plt.close(fig)
    service = [r for r in tables[files[1]] if r['case_id'] == 'WEN38']
    if not service:
        raise ValueError('WEN38 representative traces are required')
    seeds = sorted({int(r['solver_seed']) for r in service})
    fig, axes = plt.subplots(len(seeds), 2, figsize=(11, 3.4 * len(seeds)), squeeze=False, layout='constrained')
    for index, seed in enumerate(seeds):
        for model in COLORS:
            rows = sorted([r for r in service if int(r['solver_seed']) == seed and r['model'] == model], key=lambda r: int(r['period']))
            for col, metric in enumerate(['total_satisfaction', 'min_satisfaction']):
                ax = axes[index, col]
                ax.step([0] + [float(r['end_hours']) for r in rows], [0] + [float(r[metric]) for r in rows],
                        where='post', color=COLORS[model], linestyle=STYLES[model], marker=MARKERS[model],
                        markersize=4, markerfacecolor='none', alpha=.85, label=model,
                        linewidth=2.3 if model == 'Full' else 1.5)
                ax.set(title=f'Solver seed {seed}', xlabel='Period end (hours)', ylabel=metric.replace('_', ' ').capitalize(), ylim=(-.025, 1.025))
                ax.grid(alpha=.15)
        axes[index, 1].legend(ncol=2, loc='upper right')
    fig.suptitle('WEN38: representatives selected during planning\nOverlapping curves retained; No-EC may coincide with Full', fontsize=12)
    for suffix in ['png', 'pdf']:
        fig.savefig(output_dir / f'wen38_representative_service.{suffix}', dpi=180)
    plt.close(fig)
    write_json_atomic(output_dir / 'figure_manifest.json', {
        'inputs': {str((input_dir / name).resolve()): hashlib.sha256((input_dir / name).read_bytes()).hexdigest() for name in files},
        'plot_source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'paired_points': len(pairs), 'service_rows': len(service),
        'semantics': 'One point per paired solver run; period-end post-step service; overlaps retained.',
        'matplotlib_version': matplotlib.__version__,
    })


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input-dir', required=True)
    parser.add_argument('--output-dir', required=True)
    args = parser.parse_args()
    plot(args.input_dir, args.output_dir)
