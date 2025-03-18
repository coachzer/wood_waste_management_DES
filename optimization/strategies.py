from dataclasses import dataclass
from typing import Dict, List, Literal
from optimization.entity_params import (
    CollectorParams,
    TreatmentParams,
    ParamTypes,
    validate_adjustment
)

EntityType = Literal["collector", "treatment"]

@dataclass
class OptimizationAction:
    """
    Represents a specific optimization action to be applied to an entity
    
    Args:
        entity_type: Type of entity to optimize ('collector' or 'treatment')
        entity_id: Identifier for the specific entity, or 'all' for all entities
        parameter: Parameter to adjust (CollectorParams or TreatmentParams)
        adjustment: Multiplicative factor to apply to the parameter
    """
    entity_type: EntityType
    entity_id: str
    parameter: ParamTypes
    adjustment: float

    def __post_init__(self):
        """Validate action parameters after initialization"""
        if self.entity_type not in ("collector", "treatment"):
            raise ValueError(f"Invalid entity type: {self.entity_type}")

        # Validate parameter type matches entity type
        if self.entity_type == "collector" and not isinstance(self.parameter, CollectorParams):
            raise ValueError(f"Invalid parameter {self.parameter} for collector")
        if self.entity_type == "treatment" and not isinstance(self.parameter, TreatmentParams):
            raise ValueError(f"Invalid parameter {self.parameter} for treatment operator")

        # Validate and adjust the adjustment value
        self.adjustment = validate_adjustment(self.parameter, self.adjustment)


class OptimizationStrategy:
    """
    Generates optimization actions based on objective scores
    
    Args:
        threshold: Base threshold for triggering optimization actions
        aggressive: Whether to use more aggressive optimization adjustments
    """
    def __init__(self, threshold: float = 0.5, aggressive: bool = False):
        self.threshold = threshold
        self.adjustment_factor = 1.5 if aggressive else 1.2
        
        # Define score thresholds for different severity levels
        self.severity_thresholds = {
            "critical": 0.3,    # Below 30% of target
            "warning": 0.5,     # Below 50% of target
            "improvement": 0.7,  # Below 70% of target
        }

    def generate_actions(self, scores: Dict[str, float]) -> List[OptimizationAction]:
        """
        Generate optimization actions based on current scores
        
        Args:
            scores: Dictionary mapping objective names to their current scores
            
        Returns:
            List of OptimizationAction objects to be applied
        """
        actions = []
        
        # Storage utilization optimization
        if (storage_score := scores.get("StorageUtilizationObjective", 1.0)) < self.threshold:
            actions.extend(self._handle_storage_optimization(storage_score))

        # Collection efficiency optimization
        if (collection_score := scores.get("CollectionEfficiencyObjective", 1.0)) < self.threshold:
            actions.extend(self._handle_collection_optimization(collection_score))

        # Treatment efficiency optimization
        if (treatment_score := scores.get("TreatmentEfficiencyObjective", 1.0)) < self.threshold:
            actions.extend(self._handle_treatment_optimization(treatment_score))

        return actions

    def _handle_storage_optimization(self, score: float) -> List[OptimizationAction]:
        """Generate actions to optimize storage utilization"""
        actions = []
        severity = self._get_severity_level(score)
        
        # Adjust collection frequency based on severity
        freq_adjustment = self._get_adjustment_value(severity, base_reduction=0.8)
        actions.append(
            OptimizationAction(
                entity_type="collector",
                entity_id="all",
                parameter=CollectorParams.COLLECTION_FREQUENCY,
                adjustment=freq_adjustment
            )
        )

        # For critical situations, also adjust processing time
        if severity == "critical":
            actions.append(
                OptimizationAction(
                    entity_type="treatment",
                    entity_id="all",
                    parameter=TreatmentParams.PROCESSING_TIME,
                    adjustment=0.8  # Increase processing speed by reducing time
                )
            )

        return actions

    def _handle_collection_optimization(self, score: float) -> List[OptimizationAction]:
        """Generate actions to optimize collection efficiency"""
        actions = []
        severity = self._get_severity_level(score)
        
        # Adjust efficiency based on severity
        efficiency_adjustment = self._get_adjustment_value(severity, base_increase=1.2)
        actions.append(
            OptimizationAction(
                entity_type="collector",
                entity_id="all",
                parameter=CollectorParams.EFFICIENCY,
                adjustment=efficiency_adjustment
            )
        )

        return actions

    def _handle_treatment_optimization(self, score: float) -> List[OptimizationAction]:
        """Generate actions to optimize treatment efficiency"""
        actions = []
        severity = self._get_severity_level(score)
        
        # Adjust conversion rate based on severity
        rate_adjustment = self._get_adjustment_value(severity, base_increase=1.1)
        actions.append(
            OptimizationAction(
                entity_type="treatment",
                entity_id="all",
                parameter=TreatmentParams.CONVERSION_RATE,
                adjustment=rate_adjustment
            )
        )

        return actions

    def _get_severity_level(self, score: float) -> str:
        """Determine the severity level based on a score"""
        if score < self.severity_thresholds["critical"]:
            return "critical"
        elif score < self.severity_thresholds["warning"]:
            return "warning"
        elif score < self.severity_thresholds["improvement"]:
            return "improvement"
        return "normal"

    def _get_adjustment_value(
        self, 
        severity: str, 
        base_reduction: float = 1.0,
        base_increase: float = 1.0
    ) -> float:
        """Calculate adjustment value based on severity"""
        if severity == "critical":
            factor = 1.5
        elif severity == "warning":
            factor = 1.2
        elif severity == "improvement":
            factor = 1.1
        else:
            factor = 1.0
            
        # Apply the adjustment factor for aggressive mode
        factor *= self.adjustment_factor
        
        # If we're reducing (base < 1.0), we divide by the factor
        # If we're increasing (base > 1.0), we multiply by the factor
        if base_reduction != 1.0:
            return base_reduction / factor
        else:
            return base_increase * factor
