# Project Memory Bank

## Project Overview

- **Name**: Wood Waste Management DES
- **Type**: Discrete Event Simulation
- **Domain**: Resource Management / Environmental Systems
- **Primary Goal**: Simulate and optimize wood waste management systems

## Core Components

### 1. Models

- `state.py`: System state management
- `data_classes.py`: Core data structures
- `system_types.py`: System component definitions
- `facility_data.py`: Facility-related data structures
- `regional_tracker.py`: Regional data management

### 2. Core Processing

- `generator.py`: Waste generation simulation
- `collector.py`: Collection system simulation
- `treatment.py`: Treatment facility simulation
- `facility_builder.py`: Facility construction/management
- `collection_coordinator.py`: Coordination of collection activities

### 3. Monitoring & Analysis

- `data_collector.py`: Data collection and analysis
- `mfa_visualization.py`: Material flow analysis visualization

### 4. Optimization

- `optimizer.py`: Core optimization logic
- `objectives.py`: Optimization objectives
- `strategies.py`: Optimization strategies
- `stochastic.py`: Stochastic process handling

## Key Decisions & Design Patterns

### Architecture Decisions

1. Modular component-based architecture
2. Separation of core simulation from monitoring/analysis
3. Dedicated optimization module for system improvements
4. Regional data management for geographical distribution

### Data Flow

1. Waste Generation → Collection → Treatment → Demand
2. Monitoring system tracks all stages
3. Optimization feedback loop for system improvement
4. Regional tracking for geographical distribution

## Configuration Management

- `base_config.py`: Base configuration settings
- `cost_config.py`: Cost-related parameters
- `facility_config.py`: Facility configuration
- `visualization_config.py`: Visualization settings

## Visualization Capabilities

1. Ratio plots for system analysis
2. Storage visualization
3. Regional waste distribution
4. System performance metrics
5. Material flow analysis
6. Optimization results visualization

## Regional Data Management

- Storage of data for multiple regions:
  - Gorenjska
  - Goriska
  - Jugovzhodna Slovenija
  - Koroska
  - Obalno-kraska
  - Osrednjeslovenska
  - Podravska
  - Pomurska
  - Posavska
  - Primorskonotranjska
  - Savinjska
  - Zasavska

## Behavioral Model

### Storage Behavior

- Dynamic capacity management (30-85% normal utilization)
- Multi-waste type storage system
- Volume-based capacity limits
- Automatic adjustment triggers based on trend analysis

### Treatment Process

- Waste-specific transformation processes with defined efficiencies (80-98%)
- Batch processing (40% of current storage per cycle)
- Three operating states: High-Volume, Standard, and Low-Volume Processing
- Real-time process adaptation based on input quality

### Operating Modes

1. **Fixed Parameter Mode**
   - Static storage capacity
   - Fixed processing rates
   - Constant transformation efficiencies

2. **Dynamic Parameter Mode**
   - Adaptive storage capacity
   - Variable processing rates
   - Efficiency-based transformations

3. **Hybrid Mode**
   - Core parameters fixed, secondary parameters dynamic
   - Threshold-based adaptation
   - Optimal for real-world scenarios

### Performance Metrics

1. Storage Efficiency (utilization rates, capacity adjustments)
2. Treatment Efficiency (conversion rates, energy consumption)
3. System Performance (demand satisfaction, collection efficiency)
4. Model Validation through historical data and scenario testing

## Implementation Notes

### Monitoring System

- Comprehensive data collection
- Real-time analysis capabilities
- Multiple visualization options
- Ratio analysis for system performance

### Optimization Framework

- Multiple optimization strategies
- Stochastic process handling
- Enhanced visualization of results
- History tracking for optimization progress

## Future Considerations

1. Enhanced regional analysis capabilities
2. Advanced optimization strategies
3. Real-time monitoring improvements
4. Additional visualization methods

## Inventory and Overflow Management

### Inventory States

1. **Optimal Zone** (40-60% capacity)
   - Standard operations
   - Balanced collection/processing
2. **Buffer Zone** (20-40% or 60-80% capacity)
   - Adjusted operations
   - Modified collection rates
3. **Critical Zone** (<20% or >80% capacity)
   - Emergency measures
   - Priority processing/collection

### Overflow Prevention

1. **Early Warning System**
   - Storage utilization monitoring
   - Rolling window analysis
   - Predictive trend modeling
2. **Prevention Measures**
   - Dynamic capacity adjustment
   - Collection rate modification
   - Processing rate adjustment
3. **Emergency Protocols**
   - Rapid processing activation
   - Collection suspension
   - Capacity expansion

## Technical Dependencies

- Python-based implementation
- Visualization libraries for plotting
- Data analysis tools
- Optimization frameworks

## System Requirements

1. Python environment
2. Required libraries (from requirements.txt)
3. Sufficient computational resources for simulation
4. Data storage capabilities

## Documentation Structure

1. Main documentation in docs/
2. Code documentation within modules
3. Visualization outputs in plots/
4. Configuration in config/

This memory bank serves as a living document and should be updated as the project evolves.
