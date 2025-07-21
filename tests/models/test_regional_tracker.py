import pytest
from models.regional_tracker import RegionalWasteInventory, RegionalWasteTracker
from models.enums import RegionType, WasteType

@pytest.fixture
def inventory():
    return RegionalWasteInventory()

@pytest.fixture
def tracker():
    return RegionalWasteTracker()

def test_regional_waste_inventory_initialization(inventory):
    """Test RegionalWasteInventory initialization"""
    assert isinstance(inventory.inventory, dict)
    for waste_type in WasteType:
        assert inventory.get_amount(waste_type) == 0.0

def test_add_waste_to_inventory(inventory):
    """Test adding waste to inventory"""
    inventory.add_waste(WasteType.CONSTRUCTION_WOOD_17_02_01, 10.0)
    assert inventory.get_amount(WasteType.CONSTRUCTION_WOOD_17_02_01) == 10.0
    
    # Add more to existing amount
    inventory.add_waste(WasteType.CONSTRUCTION_WOOD_17_02_01, 5.0)
    assert inventory.get_amount(WasteType.CONSTRUCTION_WOOD_17_02_01) == 15.0

def test_remove_waste_from_inventory(inventory):
    """Test removing waste from inventory"""
    # Add initial amount
    inventory.add_waste(WasteType.CONSTRUCTION_WOOD_17_02_01, 10.0)
    
    # Remove partial amount
    removed = inventory.remove_waste(WasteType.CONSTRUCTION_WOOD_17_02_01, 4.0)
    assert removed == 4.0
    assert inventory.get_amount(WasteType.CONSTRUCTION_WOOD_17_02_01) == 6.0
    
    # Try to remove more than available
    removed = inventory.remove_waste(WasteType.CONSTRUCTION_WOOD_17_02_01, 8.0)
    assert removed == 6.0  # Should only remove what's available
    assert inventory.get_amount(WasteType.CONSTRUCTION_WOOD_17_02_01) == 0.0

def test_regional_waste_tracker_initialization(tracker):
    """Test RegionalWasteTracker initialization"""
    assert isinstance(tracker.regional_inventory, dict)
    for region in RegionType:
        assert region in tracker.regional_inventory
        assert isinstance(tracker.regional_inventory[region], RegionalWasteInventory)

def test_region_type_conversion(tracker):
    """Test region type conversion methods"""
    # Test with RegionType enum
    assert tracker._get_region_type(RegionType.GORENJSKA) == RegionType.GORENJSKA
    
    # Test with string (value)
    assert tracker._get_region_type("gorenjska") == RegionType.GORENJSKA
    
    # Test with string (enum name)
    assert tracker._get_region_type("GORENJSKA") == RegionType.GORENJSKA
    
    # Test invalid region
    with pytest.raises(KeyError):
        tracker._get_region_type("invalid_region")

def test_add_waste_to_region(tracker):
    """Test adding waste to a region"""
    # Add using RegionType
    tracker.add_waste(RegionType.GORENJSKA, WasteType.CONSTRUCTION_WOOD_17_02_01, 10.0)
    assert tracker.get_regional_stats(RegionType.GORENJSKA)[WasteType.CONSTRUCTION_WOOD_17_02_01] == 10.0
    
    # Add using region name string
    tracker.add_waste("gorenjska", WasteType.CONSTRUCTION_WOOD_17_02_01, 5.0)
    assert tracker.get_regional_stats("GORENJSKA")[WasteType.CONSTRUCTION_WOOD_17_02_01] == 15.0

def test_remove_waste_from_region(tracker):
    """Test removing waste from a region"""
    # Add initial amount
    tracker.add_waste(RegionType.GORENJSKA, WasteType.CONSTRUCTION_WOOD_17_02_01, 10.0)
    
    # Remove waste
    removed = tracker.remove_waste(RegionType.GORENJSKA, WasteType.CONSTRUCTION_WOOD_17_02_01, 4.0)
    assert removed == 4.0
    assert tracker.get_regional_stats(RegionType.GORENJSKA)[WasteType.CONSTRUCTION_WOOD_17_02_01] == 6.0
    
    # Try to remove from empty region
    removed = tracker.remove_waste(RegionType.GORISKA, WasteType.CONSTRUCTION_WOOD_17_02_01, 5.0)
    assert removed == 0.0

def test_get_regional_stats(tracker):
    """Test getting statistics for a region"""
    tracker.add_waste(RegionType.GORENJSKA, WasteType.CONSTRUCTION_WOOD_17_02_01, 10.0)
    tracker.add_waste(RegionType.GORENJSKA, WasteType.WOODEN_PACKAGING_15_01_03, 20.0)
    
    stats = tracker.get_regional_stats(RegionType.GORENJSKA)
    assert isinstance(stats, dict)
    assert stats[WasteType.CONSTRUCTION_WOOD_17_02_01] == 10.0
    assert stats[WasteType.WOODEN_PACKAGING_15_01_03] == 20.0
    
    # Test empty region
    empty_stats = tracker.get_regional_stats(RegionType.GORISKA)
    assert all(amount == 0.0 for amount in empty_stats.values())

def test_get_waste_type_stats(tracker):
    """Test getting statistics for a waste type across regions"""
    tracker.add_waste(RegionType.GORENJSKA, WasteType.CONSTRUCTION_WOOD_17_02_01, 10.0)
    tracker.add_waste(RegionType.GORISKA, WasteType.CONSTRUCTION_WOOD_17_02_01, 20.0)
    
    stats = tracker.get_waste_type_stats(WasteType.CONSTRUCTION_WOOD_17_02_01)
    assert isinstance(stats, dict)
    assert stats[RegionType.GORENJSKA] == 10.0
    assert stats[RegionType.GORISKA] == 20.0
    assert stats[RegionType.KOROSKA] == 0.0  # Region with no waste

def test_error_handling(tracker):
    """Test error handling for invalid inputs"""
    with pytest.raises(KeyError):
        tracker.add_waste("invalid_region", WasteType.CONSTRUCTION_WOOD_17_02_01, 10.0)
    
    with pytest.raises(KeyError):
        tracker.get_regional_stats("invalid_region")
    
    # Test with None values
    with pytest.raises(Exception):  # Either KeyError or AttributeError
        tracker.add_waste(None, WasteType.CONSTRUCTION_WOOD_17_02_01, 10.0)

def test_multiple_operations(tracker):
    """Test sequence of multiple operations"""
    # Add waste to multiple regions
    tracker.add_waste(RegionType.GORENJSKA, WasteType.CONSTRUCTION_WOOD_17_02_01, 10.0)
    tracker.add_waste(RegionType.GORISKA, WasteType.CONSTRUCTION_WOOD_17_02_01, 20.0)
    tracker.add_waste(RegionType.GORENJSKA, WasteType.WOODEN_PACKAGING_15_01_03, 15.0)
    
    # Remove waste from regions
    removed1 = tracker.remove_waste(RegionType.GORENJSKA, WasteType.CONSTRUCTION_WOOD_17_02_01, 5.0)
    removed2 = tracker.remove_waste(RegionType.GORISKA, WasteType.CONSTRUCTION_WOOD_17_02_01, 25.0)
    
    assert removed1 == 5.0
    assert removed2 == 20.0  # Only removes available amount
    
    # Verify final state
    gorenjska_stats = tracker.get_regional_stats(RegionType.GORENJSKA)
    assert gorenjska_stats[WasteType.CONSTRUCTION_WOOD_17_02_01] == 5.0
    assert gorenjska_stats[WasteType.WOODEN_PACKAGING_15_01_03] == 15.0
    
    goriska_stats = tracker.get_regional_stats(RegionType.GORISKA)
    assert goriska_stats[WasteType.CONSTRUCTION_WOOD_17_02_01] == 0.0
