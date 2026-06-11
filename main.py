from config.base_config import get_scenario_config, list_available_scenarios
from config.constants import BASELINE_OUTPUT_ROOT, DEFAULT_BASE_SEED, SCENARIO_COMPARISON_PLOTS_DIR
from core.simulation_manager import SimulationManager
from models.enums import InventoryPolicy, StockStrategy
from visualization.mfa_visualization import create_material_flow_analysis
from visualization.scenario_comparison import ScenarioComparison
from analysis.baseline_aggregate import extract_kpis, summary_rows
from persistence.serialization import build_raw_payload, jsonify
from analysis.paired_comparison import write_paired_comparison_report
from analysis.pareto import write_pareto_report
from analysis.stochastic_dominance import write_dominance_report
from visualization.pareto_visualization import write_pareto_plot
from visualization.policy_comparison_figure import write_policy_comparison_figure
from visualization.kpi_family_figures import (
    write_bullwhip_figure,
    write_carbon_figure,
    write_residence_figure,
    write_service_by_product_figure,
)
from concurrent.futures import ProcessPoolExecutor
import traceback
import argparse
import time
import json
import random
import numpy as np
from pathlib import Path

def run_single_simulation(
    scenario_name: str,
    inventory_policy: InventoryPolicy,
    stock_strategy: StockStrategy,
    seed: int | None = None,
    create_mfa: bool = True,
    raise_on_violation: bool = True,
) -> dict:
    """Run a single simulation configuration and return results.

    ``raise_on_violation`` controls the mass-balance monitor: single runs raise
    on a broken invariant; batch Monte Carlo passes ``False`` so one bad seed
    warns and continues rather than aborting the remaining replications.
    """
    print(f"\n=== Running: {scenario_name} | {inventory_policy.value} | {stock_strategy.value} ===")

    if seed is not None:

        random.seed(seed)
        np.random.seed(seed)

    try:
        scenario_config = get_scenario_config(scenario_name)

        manager = SimulationManager(seed=seed)
        manager.initialize_entities(scenario_config, inventory_policy, stock_strategy)
        manager.setup_processes(raise_on_violation=raise_on_violation)
        manager.run_simulation()

        monitor_data = manager.get_monitor_data()

        mfa_path = None
        if create_mfa:
            mfa_path = create_material_flow_analysis(
                generation_history=monitor_data["generation_history"],
                collection_history=monitor_data["collection_history"],
                processing_history=monitor_data["processing_history"],
                state=manager.state,
                scenario_name=scenario_name,
                inventory_policy=inventory_policy.value,
                stock_strategy=stock_strategy.value,
            )

        manager.facility_builder.print_failure_analysis()

        return {
            "base_scenario": scenario_name,
            "scenario_name": f"{scenario_name}_{inventory_policy.value}_{stock_strategy.value}",
            "inventory_policy": inventory_policy.value,
            "stock_strategy": stock_strategy.value,
            "seed": seed,
            "monitor_data": monitor_data,
            "mfa_path": mfa_path,
        }

    except Exception as e:
        traceback.print_exc()
        raise SystemExit(f"Simulation failed for scenario {scenario_name} with {inventory_policy.value}, {stock_strategy.value}") from e


def _run_baseline_replication_task(
    scenario_name: str,
    inventory_policy: InventoryPolicy,
    stock_strategy: StockStrategy,
    seed: int,
    replication_index: int,
    combo_dir: Path,
) -> dict:
    """Run one baseline replication and persist its artifacts.

    Module-level so it pickles under the Windows spawn start method. Artifact
    writes happen here inside the worker, so bulky monitor_data never crosses
    the process boundary; only the small KPI dict returns to the parent.
    """
    simulation_result = run_single_simulation(
        scenario_name=scenario_name,
        inventory_policy=inventory_policy,
        stock_strategy=stock_strategy,
        seed=seed,
        create_mfa=False,
        raise_on_violation=False,
    )
    kpis = extract_kpis(simulation_result["monitor_data"])

    run_path = combo_dir / f"run_{replication_index:03d}.json"
    try:
        with open(run_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "base_scenario": simulation_result["base_scenario"],
                    "scenario_name": simulation_result["scenario_name"],
                    "inventory_policy": simulation_result["inventory_policy"],
                    "stock_strategy": simulation_result["stock_strategy"],
                    "seed": simulation_result["seed"],
                    "kpis": kpis,
                },
                f,
                separators=(",", ":"),
            )
    except Exception as e:
        print(f"Warning: failed to write {run_path}: {e}")

    raw_path = combo_dir / f"raw_{replication_index:03d}.json"
    try:
        with open(raw_path, "w", encoding="utf-8") as f:
            json.dump(
                jsonify(build_raw_payload(simulation_result["monitor_data"])),
                f,
                separators=(",", ":"),
            )
    except Exception as e:
        print(f"Warning: failed to write {raw_path}: {e}")

    return {
        "base_scenario": simulation_result["base_scenario"],
        "scenario_name": simulation_result["scenario_name"],
        "inventory_policy": simulation_result["inventory_policy"],
        "stock_strategy": simulation_result["stock_strategy"],
        "seed": simulation_result["seed"],
        "replication_index": replication_index,
        "kpis": kpis,
    }


def run_monte_carlo_baseline(
    replications: int = 100,
    scenario_filter: str | None = None,
    out_root: Path | None = None,
    workers: int = 1,
) -> list[dict]:
    """
    Run baseline Monte Carlo: 100 replications per InventoryPolicy x StockStrategy.

    Returns lightweight per-replication records (no ``monitor_data``) and, when
    ``workers > 1``, uses a process pool to keep artifact writes byte-identical
    while reducing wall-clock time.

    ``out_root`` overrides where per-run artifacts are written (default
    ``outputs/baseline``), letting a caller isolate a run into its own directory
    so two invocations can be diffed without clobbering a working ``outputs/``
    dataset.
    """

    start_time = time.time()
    results: list[dict] = []

    scenarios = [scenario_filter] if scenario_filter else list_available_scenarios()
    inventory_policies = list(InventoryPolicy)
    stock_strategies = list(StockStrategy)

    print(f"\nBaseline Monte Carlo | replications={replications}")
    print(f"Scenarios: {scenarios}")
    print(f"Inventory policies: {[p.value for p in inventory_policies]}")
    print(f"Stock strategies: {[s.value for s in stock_strategies]}")

    base_seed = DEFAULT_BASE_SEED  # deterministic seed series across runs
    out_root = Path(BASELINE_OUTPUT_ROOT) if out_root is None else Path(out_root)
    out_root.mkdir(parents=True, exist_ok=True)

    for scenario_name in scenarios:
        print(f"\n{'='*60}")
        print(f"Scenario: {scenario_name}")
        print(f"{'='*60}")

        scenario_dir = out_root / scenario_name
        scenario_dir.mkdir(parents=True, exist_ok=True)

        replication_tasks: list[tuple] = []
        for policy in inventory_policies:
            for strategy in stock_strategies:
                combo_dir = scenario_dir / f"{policy.value}__{strategy.value}"
                combo_dir.mkdir(parents=True, exist_ok=True)
                for replication_index in range(replications):
                    replication_tasks.append(
                        (
                            scenario_name,
                            policy,
                            strategy,
                            base_seed + replication_index,
                            replication_index,
                            combo_dir,
                        )
                    )

        if workers <= 1:
            replication_records = [
                _run_baseline_replication_task(*task) for task in replication_tasks
            ]
        else:
            # CRN replications are independent (each worker re-seeds from its
            # own seed), so the pool only changes wall-clock, never artifacts.
            with ProcessPoolExecutor(max_workers=workers) as executor:
                futures = [
                    executor.submit(_run_baseline_replication_task, *task)
                    for task in replication_tasks
                ]
                # .result() re-raises worker failures (including SystemExit),
                # preserving the sequential abort-the-batch semantics.
                replication_records = [future.result() for future in futures]

        for policy in inventory_policies:
            for strategy in stock_strategies:
                print(f"\n-- {policy.value} x {strategy.value} --")
                combo_dir = scenario_dir / f"{policy.value}__{strategy.value}"
                combo_records = [
                    record
                    for record in replication_records
                    if record["inventory_policy"] == policy.value
                    and record["stock_strategy"] == strategy.value
                ]
                combo_records.sort(key=lambda record: record["replication_index"])
                combo_kpis = [record["kpis"] for record in combo_records]
                results.extend(combo_records)

                print(
                    f"Completed {replications} reps for {policy.value} x {strategy.value}"
                )
                summary_csv = combo_dir / "summary.csv"
                try:
                    _write_combo_summary(summary_csv, combo_kpis)
                except Exception as e:
                    print(
                        f"Warning: failed to write summary CSV for {policy.value}__{strategy.value}: {e}"
                    )

        # Paired (CRN) comparison across this scenario's combos by per-replication
        # differences, which summary.csv's marginal CIs cannot capture.
        try:
            report_path = write_paired_comparison_report(scenario_dir)
            if report_path is not None:
                print(f"Wrote paired comparison report: {report_path}")
        except Exception as e:
            print(f"Warning: failed to write paired comparison report for {scenario_name}: {e}")

        # Stochastic (FSD/SSD) dominance across this scenario's combos: a
        # distribution-level claim complementing the paired mean-difference test.
        try:
            dominance_path = write_dominance_report(scenario_dir)
            if dominance_path is not None:
                print(f"Wrote stochastic dominance report: {dominance_path}")
        except Exception as e:
            print(f"Warning: failed to write stochastic dominance report for {scenario_name}: {e}")

        # Pareto frontier over the multi-objective KPI vector (service, emissions,
        # landfill, cost), reading the summary.csv just written. The cross-scenario
        # (--root) frontier is standalone-only.
        try:
            pareto_path = write_pareto_report(scenario_dir)
            if pareto_path is not None:
                print(f"Wrote Pareto frontier: {pareto_path}")
                # Pareto frontier PDF (emissions vs service level with frontier overlay).
                plot_path = write_pareto_plot(scenario_dir)
                if plot_path is not None:
                    print(f"Wrote Pareto frontier plot: {plot_path}")
        except Exception as e:
            print(f"Warning: failed to write Pareto frontier for {scenario_name}: {e}")

        # The paper's Fig. 2 (emissions vs service level with CI crosshairs)
        # reads the summary.csv files just written; regenerating it here keeps
        # the embedded figure in sync with the latest run's numbers.
        try:
            figure_path = write_policy_comparison_figure(scenario_dir)
            if figure_path is not None:
                print(f"Wrote policy comparison figure: {figure_path}")
        except Exception as e:
            print(f"Warning: failed to write policy comparison figure for {scenario_name}: {e}")

        for kpi_figure_producer in (
            write_bullwhip_figure,
            write_residence_figure,
            write_carbon_figure,
            write_service_by_product_figure,
        ):
            try:
                kpi_fig_path = kpi_figure_producer(scenario_dir)
                if kpi_fig_path is not None:
                    print(f"Wrote {kpi_fig_path}")
            except Exception as e:
                print(f"Warning: failed to write KPI family figure for {scenario_name}: {e}")
    elapsed = time.time() - start_time
    print(
        f"\nBaseline Monte Carlo complete. Total runs: {len(results)} in {elapsed:.2f}s"
    )
    return results


def _write_combo_summary(csv_path: Path, kpis_list: list[dict]) -> None:
    # Thin writer over the pure `summary_rows` seam (issue 06): marginal KPIs
    # plus the generic `bullwhip` namespace, each with a Student-t CI (ADR 0008).
    csv_path.write_text("\n".join(summary_rows(kpis_list)), encoding="utf-8")


def main():
    """Main simulation runner - orchestrates all scenario combinations"""
    start_time = time.time()
    print(f"\n{'='*60}")
    results = []
    mfa_files = []

    scenarios = list_available_scenarios()
    inventory_policies = list(InventoryPolicy)
    stock_strategies = list(StockStrategy)
    
    print(f"Available scenarios: {scenarios}")
    print(f"Available inventory policies: {[p.value for p in inventory_policies]}")
    print(f"Available stock strategies: {[s.value for s in stock_strategies]}")
    
    total_combinations = len(scenarios) * len(inventory_policies) * len(stock_strategies)
    print(f"\nTotal simulation combinations to run: {total_combinations}")
    
    # Run all scenario combinations
    for scenario_name in scenarios:
        print(f"\n{'='*60}")
        print(f"Running base scenario: {scenario_name}")
        print(f"{'='*60}")
        
        for inventory_policy in inventory_policies:
            for stock_strategy in stock_strategies:
                result = run_single_simulation(
                    scenario_name, inventory_policy, stock_strategy,
                    seed=DEFAULT_BASE_SEED,
                )
                results.append(result)
                mfa_files.append(result["mfa_path"])
    
    print(f"\n{'='*60}")
    print("Creating scenario comparison visualizations")
    print(f"{'='*60}")
    comparison = ScenarioComparison(results)
    comparison.create_storage_heatmaps()
    comparison.create_temporal_comparison()
    comparison.create_cost_impact_comparison()
    comparison.create_summary_dashboard()
    print(f"Scenario comparison visualizations saved to {SCENARIO_COMPARISON_PLOTS_DIR}/")

    print(f"\n{'='*60}")
    print("SIMULATION BATCH COMPLETE")
    print(f"{'='*60}")
    print(f"Total simulations run: {len(results)}")
    print(f"Base scenarios: {len(scenarios)}")
    print(f"Strategy combinations per base scenario: {len(inventory_policies) * len(stock_strategies)}")

    print("\nMFA Visualizations Created:")
    for mfa_path in mfa_files:
        print(f"  {mfa_path}")
        
    print(f"\n{'='*60}")
    print("All simulations completed successfully!")
    print(f"Results saved to: {len(results)} simulation results")
    print(f"Material Flow Analysis files saved to: {len(mfa_files)} MFA files")
    print(f"\nTotal execution time: {time.time() - start_time:.2f} seconds")    

    return results

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode",
        choices=["grid", "baseline"],
        default="grid",
        help="grid = single run per combo; baseline = 100 Monte Carlo replications per combo",
    )
    parser.add_argument(
        "--replications",
        type=int,
        default=100,
        help="Replications per combo for baseline mode",
    )
    parser.add_argument(
        "--scenario",
        type=str,
        default=None,
        help="Run only this scenario name (optional)",
    )
    parser.add_argument(
        "--out-root",
        type=str,
        default=None,
        help=f"Override the baseline output root (default: {BASELINE_OUTPUT_ROOT}). "
        "Isolates a run from a working outputs/ dataset.",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Worker processes for baseline replications (default 1 = sequential). "
        "Artifacts are byte-identical at any worker count; only wall-clock changes.",
    )
    args = parser.parse_args()

    if args.mode == "baseline":
        _ = run_monte_carlo_baseline(
            replications=args.replications,
            scenario_filter=args.scenario,
            out_root=args.out_root,
            workers=args.workers,
        )
    else:
        all_results = main()
