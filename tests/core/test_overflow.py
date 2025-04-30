import pytest
import simpy
from core.overflow import OverflowTracker, OverflowStrategy
from models.enums import WasteType
from core.treatment import TreatmentOperator
from core.collector import CollectorCompany
from core.generator import WasteGenerator
from monitoring.data_collector import DataCollector

@pytest.fixture
def env():
    return simpy.Environment()

@pytest.fixture
def data_collector(env):
    return DataCollector(env)

@pytest.fixture
def overflow_tracker():
    return OverflowTracker()

@pytest.fixture
def basic_treatment(env, data_collector):
    """Treatment facility with limited capacity"""
    return TreatmentOperator(
        env=env,
        name="TestTreatment",
        processing_time=1.0,
        storage_capacity=100.0,  # Small capacity to test overflow
        energy_consumption=50.0,
        environmental_impact=1.0,
        conversion_rate=0.8,
        operational_costs=100.0,
        region="GORENJSKA",
        data_collector=data_collector
    )

def test_overflow_tracking_with_strategies(overflow_tracker):
    """Test overflow tracking with different strategies"""
    
    # Verify landfill tracking
    assert overflow_tracker.landfill_history["generator"] == 10.0
    assert overflow_tracker.total_landfilled == 10.0  # Only landfill strategy adds to total
    
    # Verify costs for different strategies
    stats = overflow_tracker.get_overflow_statistics()
    assert stats["total_landfilled"] == 10.0
    assert stats["total_expansion_costs"] == 15.0 * overflow_tracker.storage_expansion_cost
    assert stats["total_transport_costs"] == 20.0 * overflow_tracker.emergency_transport_cost

def test_invalid_facility_type(overflow_tracker):
    """Test handling of invalid facility types"""
    with pytest.raises(ValueError):
        overflow_tracker.track_overflow("invalid_type", 10.0)

def test_overflow_strategies_cost_comparison(overflow_tracker):
    """Test cost comparison between different overflow strategies"""
    volume = 20.0
    
    # Try each strategy with the same volume
    landfill_cost, _ = overflow_tracker.track_overflow("treatment", volume, OverflowStrategy.LANDFILL)
    expansion_cost, _ = overflow_tracker.track_overflow("treatment", volume, OverflowStrategy.EXPAND_STORAGE)
    transport_cost, _ = overflow_tracker.track_overflow("treatment", volume, OverflowStrategy.EMERGENCY_TRANSPORT)
    reduction_cost, _ = overflow_tracker.track_overflow("treatment", volume, OverflowStrategy.REDUCE_INTAKE)
    
    # Verify cost relationships
    assert transport_cost > expansion_cost  # Emergency transport should be most expensive
    assert expansion_cost > landfill_cost  # Storage expansion more expensive than landfill
    assert reduction_cost == 0.0  # Intake reduction has no direct cost

def test_treatment_facility_overflow(basic_treatment):
    """Test overflow handling in treatment facility"""
    # Try to add more waste than capacity
    excess_amount = basic_treatment.storage_capacity + 50.0
    initial_waste = {
        WasteType.CONSTRUCTION_WOOD: excess_amount
    }
    
    # Set waste storage and verify overflow is tracked
    basic_treatment.waste_storage = initial_waste
    
    # Verify storage constraints
    assert basic_treatment.current_storage <= basic_treatment.storage_capacity
    
    # Verify overflow was tracked through data collector
    storage_records = basic_treatment.data_collector.get_overflow_records()
    assert len(storage_records) > 0
    assert sum(record["volume"] for record in storage_records) == 50.0

def test_strategy_message_formatting(overflow_tracker):
    """Test the messages returned by different strategies"""
    # Test message formatting for each strategy
    _, landfill_msg = overflow_tracker.track_overflow("generator", 5.0, OverflowStrategy.LANDFILL)
    _, expand_msg = overflow_tracker.track_overflow("collector", 10.0, OverflowStrategy.EXPAND_STORAGE)
    _, transport_msg = overflow_tracker.track_overflow("treatment", 15.0, OverflowStrategy.EMERGENCY_TRANSPORT)
    _, reduce_msg = overflow_tracker.track_overflow("generator", 20.0, OverflowStrategy.REDUCE_INTAKE)
    
    # Verify message formatting
    assert "landfill" in landfill_msg.lower() and "warning" in landfill_msg.lower()
    assert "expanded storage" in expand_msg.lower() and "10.00" in expand_msg
    assert "emergency transported" in transport_msg.lower() and "15.00" in transport_msg
    assert "reduced intake" in reduce_msg.lower() and "20.00" in reduce_msg

def test_severity_based_penalty_escalation(overflow_tracker):
    """Test that penalties escalate correctly with overflow severity"""
    # Test increasing volumes with same strategy
    cost1, _ = overflow_tracker.track_overflow("treatment", 5.0, OverflowStrategy.LANDFILL)
    cost2, _ = overflow_tracker.track_overflow("treatment", 25.0, OverflowStrategy.LANDFILL)
    cost3, _ = overflow_tracker.track_overflow("treatment", 50.0, OverflowStrategy.LANDFILL)
    
    # Costs should escalate non-linearly due to severity multipliers
    assert cost3 / 50.0 > cost2 / 25.0 > cost1 / 5.0

def test_cumulative_cost_tracking(overflow_tracker):
    """Test tracking of cumulative costs across different strategies"""
    # Use each strategy multiple times
    for _ in range(2):
        overflow_tracker.track_overflow("treatment", 10.0, OverflowStrategy.LANDFILL)
        overflow_tracker.track_overflow("treatment", 10.0, OverflowStrategy.EXPAND_STORAGE)
        overflow_tracker.track_overflow("treatment", 10.0, OverflowStrategy.EMERGENCY_TRANSPORT)
    
    stats = overflow_tracker.get_overflow_statistics()
    
    # Verify cumulative costs
    assert stats["total_landfilled"] == 20.0
    assert stats["total_expansion_costs"] == 20.0 * overflow_tracker.storage_expansion_cost
    assert stats["total_transport_costs"] == 20.0 * overflow_tracker.emergency_transport_cost
    assert stats["total_cost"] == sum([
        stats["total_penalties"],
        stats["total_expansion_costs"],
        stats["total_transport_costs"]
    ])
