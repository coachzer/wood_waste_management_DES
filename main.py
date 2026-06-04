from datetime import time
from config.base_config import get_scenario_with_strategies, list_available_scenarios
from core.facility_builder import print_failure_analysis
from core.simulation_manager import SimulationManager
from models.enums import InventoryPolicy, StockStrategy
from monitoring.mfa_visualization import create_material_flow_analysis
from monitoring.scenario_comparison import ScenarioComparison
from monitoring.baseline_aggregate import extract_kpis, summary_rows
from monitoring.paired_comparison import write_paired_comparison_report
from monitoring.pareto import write_pareto_report
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
        scenario_config = get_scenario_with_strategies(
            base_scenario_name=scenario_name,
            inventory_policy=inventory_policy,
            stock_strategy=stock_strategy
        )

        manager = SimulationManager(seed=seed)
        manager.initialize_entities(scenario_config)
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

        print_failure_analysis()

        return {
            "base_scenario": scenario_name,
            "scenario_name": scenario_config.name,
            "inventory_policy": inventory_policy.value,
            "stock_strategy": stock_strategy.value,
            "seed": seed,
            "monitor_data": monitor_data,
            "mfa_path": mfa_path,
        }

    except Exception as e:
        traceback.print_exc()
        raise SystemExit(f"Simulation failed for scenario {scenario_name} with {inventory_policy.value}, {stock_strategy.value}") from e


def run_monte_carlo_baseline(
    replications: int = 100,
    scenario_filter: str | None = None,
    out_root: Path | None = None,
) -> list[dict]:
    """
    Run baseline Monte Carlo: 100 replications per InventoryPolicy x StockStrategy.

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

    base_seed = 123456  # deterministic seed series across runs
    out_root = Path("outputs") / "baseline" if out_root is None else Path(out_root)
    out_root.mkdir(parents=True, exist_ok=True)

    for scenario_name in scenarios:
        print(f"\n{'='*60}")
        print(f"Scenario: {scenario_name}")
        print(f"{'='*60}")

        scenario_dir = out_root / scenario_name
        scenario_dir.mkdir(parents=True, exist_ok=True)

        for policy in inventory_policies:
            for strategy in stock_strategies:
                print(f"\n-- {policy.value} x {strategy.value} --")
                combo_dir = scenario_dir / f"{policy.value}__{strategy.value}"
                combo_dir.mkdir(parents=True, exist_ok=True)
                combo_kpis: list[dict] = []
                for i in range(replications):
                    seed = base_seed + i
                    res = run_single_simulation(
                        scenario_name=scenario_name,
                        inventory_policy=policy,
                        stock_strategy=strategy,
                        seed=seed,
                        create_mfa=False,
                        raise_on_violation=False,
                    )
                    results.append(res)
                    kpis = extract_kpis(res["monitor_data"])
                    combo_kpis.append(kpis)
                    # Persist per-run KPIs (avoid raw monitor_data with Enums)
                    run_path = combo_dir / f"run_{i:03d}.json"
                    try:
                        with open(run_path, "w", encoding="utf-8") as f:
                            json.dump(
                                {
                                    "base_scenario": res["base_scenario"],
                                    "scenario_name": res["scenario_name"],
                                    "inventory_policy": res["inventory_policy"],
                                    "stock_strategy": res["stock_strategy"],
                                    "seed": res["seed"],
                                    "kpis": kpis,
                                },
                                f,
                                separators=(",", ":"),
                            )
                    except Exception as e:
                        print(f"Warning: failed to write {run_path}: {e}")

                print(
                    f"Completed {replications} reps for {policy.value} x {strategy.value}"
                )
                # Write per-combo summary CSV
                summary_csv = combo_dir / "summary.csv"
                try:
                    _write_combo_summary(summary_csv, combo_kpis)
                except Exception as e:
                    print(
                        f"Warning: failed to write summary CSV for {policy.value}__{strategy.value}: {e}"
                    )

        # Paired (CRN) comparison across all combos in this scenario. Exploits the
        # shared seed series to compare combos by per-replication differences,
        # which summary.csv's marginal CIs cannot. (monitoring/paired_comparison.py)
        try:
            report_path = write_paired_comparison_report(scenario_dir)
            if report_path is not None:
                print(f"Wrote paired comparison report: {report_path}")
        except Exception as e:
            print(f"Warning: failed to write paired comparison report for {scenario_name}: {e}")

        # Pareto frontier across this scenario's combos over the multi-objective
        # KPI vector (service, emissions, landfill, cost), reading the summary.csv
        # means just written. Reports the non-dominated set so a combo that wins on
        # one objective by losing on others cannot pass for a winner. The
        # cross-scenario (--root) frontier is standalone-only. (monitoring/pareto.py)
        try:
            pareto_path = write_pareto_report(scenario_dir)
            if pareto_path is not None:
                print(f"Wrote Pareto frontier: {pareto_path}")
        except Exception as e:
            print(f"Warning: failed to write Pareto frontier for {scenario_name}: {e}")
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
                # Run single simulation
                result = run_single_simulation(scenario_name, inventory_policy, stock_strategy)
                results.append(result)
                mfa_files.append(result["mfa_path"])
    
    # Create comparison visualizations
    print(f"\n{'='*60}")
    print("Creating scenario comparison visualizations")
    print(f"{'='*60}")
    comparison = ScenarioComparison(results)
    comparison.create_storage_heatmaps()
    comparison.create_temporal_comparison()
    comparison.create_cost_impact_comparison()
    comparison.create_summary_dashboard()
    print("Scenario comparison visualizations saved to plots/scenario_comparison/")

    # Print summary
    print(f"\n{'='*60}")
    print("SIMULATION BATCH COMPLETE")
    print(f"{'='*60}")
    print(f"Total simulations run: {len(results)}")
    print(f"Base scenarios: {len(scenarios)}")
    print(f"Strategy combinations per base scenario: {len(inventory_policies) * len(stock_strategies)}")

    # Print MFA files
    print("\nMFA Visualizations Created:")
    for mfa_path in mfa_files:
        print(f"  {mfa_path}")
        
    # Print total execution time
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
        help="Override the baseline output root (default: outputs/baseline). "
        "Isolates a run from a working outputs/ dataset.",
    )
    args = parser.parse_args()

    if args.mode == "baseline":
        _ = run_monte_carlo_baseline(
            replications=args.replications,
            scenario_filter=args.scenario,
            out_root=args.out_root,
        )
    else:
        all_results = main()
