from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
import numpy as np
from optimization.uncertainty.scenarios import ScenarioGenerator, ScenarioGenerationError

@dataclass
class OptimizationStage:
    """
    Results of a single optimization stage
    
    Args:
        decisions: Dictionary of optimization decisions
        costs: Dictionary of associated costs
        metrics: Dictionary of performance metrics
    """
    decisions: Dict[str, Any]
    costs: Dict[str, float]
    metrics: Dict[str, Any]

@dataclass
class StochasticOptimizationResult:
    """
    Results of two-stage stochastic optimization
    
    Args:
        first_stage: First stage (strategic) optimization results
        second_stage: List of second stage (operational) results for each scenario
        expected_cost: Expected total cost across all scenarios
        risk_measure: Value at Risk or other risk metric
        metrics: Additional performance metrics
    """
    first_stage: OptimizationStage
    second_stage: List[OptimizationStage]
    expected_cost: float
    risk_measure: float
    metrics: Dict[str, Any]

class StochasticOptimizer:
    """
    Implements two-stage stochastic optimization
    
    This class handles the optimization process across multiple scenarios,
    balancing first-stage strategic decisions with second-stage operational
    decisions.
    
    Args:
        scenario_generator: Generator for stochastic scenarios
        min_scenarios: Minimum number of scenarios to evaluate
        max_iterations: Maximum optimization iterations
        convergence_threshold: Threshold for optimization convergence
    """
    def __init__(
        self,
        scenario_generator: ScenarioGenerator,
        min_scenarios: int = 50,
        max_iterations: int = 100,
        convergence_threshold: float = 0.01
    ):
        self.scenario_generator = scenario_generator
        self.min_scenarios = min_scenarios
        self.max_iterations = max_iterations
        self.convergence_threshold = convergence_threshold
        
        # Track optimization progress
        self._iteration_history: List[Dict] = []
        self._best_solution: Optional[StochasticOptimizationResult] = None

    def optimize(
        self,
        risk_aversion: float = 0.5,
        facility_constraints: Optional[Dict] = None
    ) -> StochasticOptimizationResult:
        """
        Perform two-stage stochastic optimization
        
        Args:
            risk_aversion: Risk aversion parameter (0-1)
            facility_constraints: Optional constraints on facility decisions
            
        Returns:
            StochasticOptimizationResult containing optimization results
            
        Raises:
            ValueError: If parameters are invalid
            ScenarioGenerationError: If scenario generation fails
        """
        if not 0 <= risk_aversion <= 1:
            raise ValueError("Risk aversion must be between 0 and 1")

        # Generate scenarios
        try:
            scenarios = self.scenario_generator.generate_scenarios()
        except ScenarioGenerationError as e:
            raise ScenarioGenerationError(f"Failed to generate scenarios: {str(e)}")

        if len(scenarios) < self.min_scenarios:
            raise ValueError(
                f"Too few scenarios generated ({len(scenarios)}, minimum {self.min_scenarios})"
            )

        best_cost = float('inf')
        best_result = None

        # Iterative optimization
        for iteration in range(self.max_iterations):
            # First stage optimization
            first_stage = self._optimize_first_stage(
                scenarios, risk_aversion, facility_constraints
            )
            
            # Second stage optimization
            second_stage_results = []
            scenario_costs = []
            
            for scenario in scenarios:
                try:
                    stage_result = self._optimize_second_stage(
                        first_stage, scenario, facility_constraints
                    )
                    second_stage_results.append(stage_result)
                    scenario_costs.append(
                        stage_result.costs["total"] * scenario["probability"]
                    )
                except Exception as e:
                    print(f"Warning: Failed to optimize scenario: {str(e)}")
                    continue

            if not scenario_costs:
                raise ValueError("No valid scenarios could be evaluated")

            # Calculate expected cost and risk measure
            expected_cost = sum(scenario_costs)
            risk_measure = self._calculate_risk_measure(scenario_costs, risk_aversion)
            
            # Record iteration results
            iteration_result = StochasticOptimizationResult(
                first_stage=first_stage,
                second_stage=second_stage_results,
                expected_cost=expected_cost,
                risk_measure=risk_measure,
                metrics=self._calculate_metrics(first_stage, second_stage_results)
            )
            
            self._record_iteration(iteration_result)

            # Check for improvement
            if expected_cost < best_cost:
                best_cost = expected_cost
                best_result = iteration_result
            
            # Check convergence
            if self._check_convergence(iteration):
                break

        if best_result is None:
            raise ValueError("Optimization failed to find valid solution")

        self._best_solution = best_result
        return best_result

    def _optimize_first_stage(
        self,
        scenarios: List[Dict],
        risk_aversion: float,
        constraints: Optional[Dict]
    ) -> OptimizationStage:
        """
        Optimize first-stage (strategic) decisions
        
        This includes facility locations, capacities, and other long-term decisions
        that must be made before scenarios are realized.
        """
        # TODO: Implement proper facility location and capacity optimization
        # For now, return a basic solution
        decisions = {
            "facility_locations": [],
            "storage_capacities": {},
            "processing_rates": {},
        }
        
        costs = {
            "facility_setup": 1000.0,
            "capacity_cost": 500.0,
            "total": 1500.0
        }
        
        metrics = {
            "num_facilities": 0,
            "total_capacity": 0.0,
            "coverage_ratio": 0.0
        }
        
        return OptimizationStage(decisions, costs, metrics)

    def _optimize_second_stage(
        self,
        first_stage: OptimizationStage,
        scenario: Dict,
        constraints: Optional[Dict]
    ) -> OptimizationStage:
        """
        Optimize second-stage (operational) decisions for a scenario
        
        This includes routing, processing rates, and other operational decisions
        that can be adjusted based on the realized scenario.
        """
        # TODO: Implement proper operational optimization
        # For now, return placeholder values
        decisions = {
            "routing": {},
            "processing_rates": {},
            "storage_levels": {},
        }
        
        costs = {
            "operational": 800.0,
            "transportation": 200.0,
            "total": 1000.0
        }
        
        metrics = {
            "utilization": 0.7,
            "efficiency": 0.8,
            "service_level": 0.9
        }
        
        return OptimizationStage(decisions, costs, metrics)

    def _calculate_risk_measure(
        self, costs: List[float], risk_aversion: float
    ) -> float:
        """Calculate risk measure (e.g., Value at Risk) from scenario costs"""
        if not costs:
            return 0.0
            
        var_95 = np.percentile(costs, 95)  # 95th percentile VaR
        cvar_95 = np.mean([c for c in costs if c >= var_95])  # CVaR
        
        return (1 - risk_aversion) * np.mean(costs) + risk_aversion * cvar_95

    def _calculate_metrics(
        self,
        first_stage: OptimizationStage,
        second_stage: List[OptimizationStage]
    ) -> Dict[str, Any]:
        """Calculate performance metrics for the optimization"""
        if not second_stage:
            return {}
            
        metrics = {
            "first_stage_cost": first_stage.costs["total"],
            "avg_second_stage_cost": np.mean(
                [stage.costs["total"] for stage in second_stage]
            ),
            "num_scenarios_evaluated": len(second_stage),
            "avg_utilization": np.mean(
                [stage.metrics["utilization"] for stage in second_stage]
            ),
            "avg_efficiency": np.mean(
                [stage.metrics["efficiency"] for stage in second_stage]
            ),
        }
        
        return metrics

    def _record_iteration(self, result: StochasticOptimizationResult) -> None:
        """Record iteration results in history"""
        self._iteration_history.append({
            "expected_cost": result.expected_cost,
            "risk_measure": result.risk_measure,
            "metrics": result.metrics
        })

    def _check_convergence(self, iteration: int) -> bool:
        """Check if optimization has converged"""
        if iteration < 2:
            return False
            
        recent_costs = [
            result["expected_cost"] 
            for result in self._iteration_history[-3:]
        ]
        
        if len(recent_costs) < 3:
            return False
            
        # Check if cost improvement is below threshold
        improvements = [
            abs(recent_costs[i] - recent_costs[i-1]) / recent_costs[i-1]
            for i in range(1, len(recent_costs))
        ]
        
        return all(imp < self.convergence_threshold for imp in improvements)

    def get_optimization_history(self) -> List[Dict]:
        """Get history of optimization iterations"""
        return self._iteration_history.copy()

    def get_best_solution(self) -> Optional[StochasticOptimizationResult]:
        """Get the best solution found during optimization"""
        return self._best_solution
