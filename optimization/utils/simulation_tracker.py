"""Utilities for tracking and analyzing simulation parameters and results"""
from dataclasses import dataclass
from typing import Dict, List, Optional
import numpy as np
from datetime import datetime
import json
import os

@dataclass
class SimulationSnapshot:
    """Captures the state of simulation parameters at a point in time"""
    timestamp: float
    collection_rates: Dict[str, float]
    processing_rates: Dict[str, float]
    storage_levels: Dict[str, float]
    objective_scores: Dict[str, float]
    metrics: Dict[str, float]

class SimulationTracker:
    """
    Tracks and analyzes simulation parameters and results over time
    
    This class provides utilities for:
    - Recording simulation state snapshots
    - Analyzing parameter evolution
    - Saving and loading simulation history
    - Generating summary statistics
    """
    
    def __init__(self):
        self.snapshots: List[SimulationSnapshot] = []
        self.metadata: Dict = {
            "start_time": datetime.now().isoformat(),
            "description": "",
            "tags": []
        }

    def add_snapshot(
        self,
        timestamp: float,
        collection_rates: Dict[str, float],
        processing_rates: Dict[str, float],
        storage_levels: Dict[str, float],
        objective_scores: Dict[str, float],
        metrics: Optional[Dict[str, float]] = None
    ) -> None:
        """Add a new simulation state snapshot"""
        snapshot = SimulationSnapshot(
            timestamp=timestamp,
            collection_rates=collection_rates,
            processing_rates=processing_rates,
            storage_levels=storage_levels,
            objective_scores=objective_scores,
            metrics=metrics or {}
        )
        self.snapshots.append(snapshot)

    def get_parameter_evolution(self, parameter_name: str) -> Dict[str, List[float]]:
        """Get the evolution of a specific parameter over time"""
        evolution = {
            "timestamps": [],
            "values": []
        }
        
        for snapshot in self.snapshots:
            evolution["timestamps"].append(snapshot.timestamp)
            # Look for parameter in different dictionaries
            value = None
            if parameter_name in snapshot.collection_rates:
                value = snapshot.collection_rates[parameter_name]
            elif parameter_name in snapshot.processing_rates:
                value = snapshot.processing_rates[parameter_name]
            elif parameter_name in snapshot.storage_levels:
                value = snapshot.storage_levels[parameter_name]
            elif parameter_name in snapshot.objective_scores:
                value = snapshot.objective_scores[parameter_name]
            elif parameter_name in snapshot.metrics:
                value = snapshot.metrics[parameter_name]
                
            evolution["values"].append(value if value is not None else 0.0)
            
        return evolution

    def calculate_statistics(self) -> Dict[str, Dict[str, float]]:
        """Calculate summary statistics for all parameters"""
        stats = {
            "collection_rates": {},
            "processing_rates": {},
            "storage_levels": {},
            "objective_scores": {},
            "metrics": {}
        }
        
        if not self.snapshots:
            return stats
            
        # Get all unique parameter names
        parameters = set()
        for snapshot in self.snapshots:
            parameters.update(snapshot.collection_rates.keys())
            parameters.update(snapshot.processing_rates.keys())
            parameters.update(snapshot.storage_levels.keys())
            parameters.update(snapshot.objective_scores.keys())
            parameters.update(snapshot.metrics.keys())
            
        # Calculate statistics for each parameter
        for param in parameters:
            evolution = self.get_parameter_evolution(param)
            values = evolution["values"]
            
            param_stats = {
                "mean": np.mean(values),
                "std": np.std(values),
                "min": np.min(values),
                "max": np.max(values),
                "final": values[-1] if values else 0.0,
                "change": values[-1] - values[0] if len(values) > 1 else 0.0
            }
            
            # Determine parameter type and store stats
            if param in self.snapshots[0].collection_rates:
                stats["collection_rates"][param] = param_stats
            elif param in self.snapshots[0].processing_rates:
                stats["processing_rates"][param] = param_stats
            elif param in self.snapshots[0].storage_levels:
                stats["storage_levels"][param] = param_stats
            elif param in self.snapshots[0].objective_scores:
                stats["objective_scores"][param] = param_stats
            elif param in self.snapshots[0].metrics:
                stats["metrics"][param] = param_stats
                
        return stats

    def save_history(self, filepath: str) -> None:
        """Save simulation history to a JSON file"""
        data = {
            "metadata": self.metadata,
            "snapshots": [
                {
                    "timestamp": s.timestamp,
                    "collection_rates": s.collection_rates,
                    "processing_rates": s.processing_rates,
                    "storage_levels": s.storage_levels,
                    "objective_scores": s.objective_scores,
                    "metrics": s.metrics
                }
                for s in self.snapshots
            ]
        }
        
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)

    def load_history(self, filepath: str) -> None:
        """Load simulation history from a JSON file"""
        with open(filepath, 'r') as f:
            data = json.load(f)
            
        self.metadata = data["metadata"]
        self.snapshots = [
            SimulationSnapshot(
                timestamp=s["timestamp"],
                collection_rates=s["collection_rates"],
                processing_rates=s["processing_rates"],
                storage_levels=s["storage_levels"],
                objective_scores=s["objective_scores"],
                metrics=s["metrics"]
            )
            for s in data["snapshots"]
        ]

    def get_summary(self) -> Dict:
        """Get a summary of the simulation run"""
        if not self.snapshots:
            return {"error": "No simulation data available"}
            
        stats = self.calculate_statistics()
        
        return {
            "metadata": self.metadata,
            "duration": self.snapshots[-1].timestamp - self.snapshots[0].timestamp,
            "num_snapshots": len(self.snapshots),
            "final_objective_scores": self.snapshots[-1].objective_scores,
            "statistics": stats,
            "final_metrics": self.snapshots[-1].metrics
        }

    def add_metadata(self, description: str, tags: List[str]) -> None:
        """Add metadata about the simulation run"""
        self.metadata["description"] = description
        self.metadata["tags"] = tags
