# Discrete Event Wood Waste Management Simulation

A Python-based simulation system for modeling and optimizing wood waste management operations. The system simulates waste generation, collection, and treatment processes while providing comprehensive monitoring and optimization capabilities.

## Project Structure

```
├── core/               # Core simulation components
│   ├── generator.py    # Waste generation simulation
│   ├── collector.py    # Collection process simulation
│   └── treatment.py    # Treatment facility simulation
├── models/             # Data models and configurations
│   ├── config.py       # System configuration
│   ├── data_classes.py # Data structure definitions
│   ├── enums.py       # Enumeration definitions
│   └── state.py       # State management
├── monitoring/         # Monitoring and visualization
│   ├── monitor.py      # System monitoring
│   └── mfa_visualization.py # Material flow analysis
├── optimization/       # System optimization
│   ├── objectives.py   # Optimization objectives
│   ├── optimizer.py    # Main optimizer
│   ├── stochastic.py   # Stochastic optimization
│   └── strategies.py   # Optimization strategies
└── utils/             # Utility functions
    └── helpers.py     # Helper functions
```

## Installation & Setup

1. Clone the repository
2. Create a virtual environment (recommended):

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install required dependencies:

```bash
pip install -r requirements.txt
```

4. Configure the simulation:

   - Adjust parameters in `models/config.py`
   - Modify enumeration values in `models/enums.py`
   - Update state definitions in `models/state.py`

5. Run the simulation:

```bash
python main.py
```

The system will generate visualizations and metrics in the `plots/` directory.

## Features

### Core Components

- **Waste Generation**: Simulates multiple waste generators with:
  - Configurable waste types (sawdust, wood cuttings, bark, etc.)
  - Dynamic generation rates with seasonal factors and stochastic variations
  - Advanced storage capacity management with dynamic adjustments
  - Priority-based collection scheduling with automatic adjustment
  - Multi-level state monitoring and operational control
  - Regional waste distribution and prioritization

- **Waste Collection**: Models collection operations with:
  - Multiple collection strategies:
    - Collaborative Strategy: Collectors work together within assigned regions, coordinating with other available collectors to handle waste collection efficiently. When a collector operates collaboratively, it first allows other collectors to process waste, then handles any remaining volume itself. This approach optimizes resource utilization and ensures balanced workload distribution across the collection fleet.
    - Competitive Strategy: Collectors operate independently, targeting high-priority generators first. Each collector dynamically adjusts its collection capacity based on efficiency ratings and modifies transport costs accordingly. This creates a performance-driven system where collectors compete for waste from prioritized generators while balancing operational costs.
  - Regional-based collection routing with availability checking
  - Transport cost optimization with efficiency modulation
  - Collection efficiency tracking and performance monitoring
  - Dynamic demand-based scheduling with storage level adjustments
  - Storage-aware collection rate modification (80-120% base demand)
  - Threshold-based collection triggers with regional prioritization

- **Treatment Processing**: Simulates treatment facilities with:
  - Waste-specific transformation processes with defined efficiencies:
    - Sawdust → Mixed Wood (95% efficiency)
    - Wood Cuttings → Mixed Wood (90% efficiency)
    - Bark → Mixed Wood (85% efficiency)
    - Cork → Mixed Wood (92% efficiency)
    - Solid Wood → Mixed Wood (98% efficiency)
    - Paper Packaging → Mixed Wood (80% efficiency)
    - Wood Packaging → Mixed Wood (88% efficiency)
  - Storage management with dynamic capacity
  - Batch processing (40% of current storage per cycle)
  - Real-time energy consumption tracking
  - Quality-dependent conversion rates with stochastic variations
  - Early warning system for overflow prevention

### System States & Behavior

- **Storage States**:
  - Normal Operation (30-85% utilization)
    - Standard processing rates
    - Balanced collection requests
  - Near-Capacity Operations (>85%)
    - Accelerated processing (30% faster)
    - Reduced collection
    - Capacity expansion triggered
  - Under-Utilization Handling (<30%)
    - Slowed processing (30% slower)
    - Increased collection
    - Capacity contraction considered

- **Inventory States**:
  - Optimal Zone (40-60% capacity)
    - Standard operations
    - Balanced collection/processing
  - Buffer Zone (20-40% or 60-80% capacity)
    - Adjusted operations
    - Modified collection rates
  - Critical Zone (<20% or >80% capacity)
    - Emergency measures
    - Extreme rate adjustments

- **Treatment States**:
  - High-Volume Processing (>80% capacity)
    - Increased processing capacity
    - Higher energy consumption
  - Standard Processing (20-80% capacity)
    - Normal operation mode
    - Balanced energy usage
  - Low-Volume Processing (<20% capacity)
    - Reduced processing capacity
    - Energy conservation

### Monitoring System

- **Real-time Tracking**:
  - Generation rates and volumes
  - Collection efficiency
  - Storage utilization
  - Processing performance
  - Environmental impact metrics

- **Visualization**:
  - Material Flow Analysis (MFA)
  - Generation trends and patterns
  - Collection efficiency metrics
  - Storage level analysis
  - System performance indicators
  - Treatment process monitoring
  - Optimization progress tracking

### Available Visualizations

The system generates comprehensive visualizations in the `plots/` directory:

- **Generation Analysis**:
  - Generation trends over time
  - Time-specific snapshots (t100, t500)
  - Generator performance metrics

- **Collection Analysis**:
  - Collection efficiency metrics
  - Time-based collection analysis
  - Collector performance indicators

- **Storage Analysis**:
  - Detailed storage utilization
  - Time-specific storage states
  - Storage efficiency metrics

- **Treatment Analysis**:
  - Processing volume analysis
  - Treatment metrics
  - Detailed treatment monitoring

- **System Analysis**:
  - Material Flow Analysis (MFA)
  - System efficiency metrics
  - Production analysis
  - Cumulative performance tracking

### Optimization System

The optimization module (`optimization/`) provides comprehensive system optimization:

- **Optimization Objectives** (`objectives.py`):
  - Storage utilization optimization
  - Collection route optimization
  - Treatment process optimization
  - Environmental impact minimization
  - Energy consumption reduction
  - Resource utilization maximization

- **Optimization Strategies** (`strategies.py`):
  - Multi-objective optimization
  - Stochastic optimization approaches
  - Constraint-based optimization
  - Dynamic parameter adjustment
  - Adaptive strategy selection

- **Optimization History** (`optimization_history.py`):
  - Progress tracking
  - Performance metrics logging
  - Improvement visualization
  - Strategy effectiveness analysis

- **Visualization** (`visualization.py`):
  - Optimization progress plots
  - Performance comparison charts
  - Strategy effectiveness visualization
  - Parameter sensitivity analysis

## Documentation

Detailed documentation is available in the `docs/` directory:

### Behavior Model (`docs/behavior_model.md`)

Comprehensive documentation of system states, transitions, and behaviors:

- Storage behavior models and capacity management
- Treatment process models and efficiency optimization
- Inventory management strategies
- Production control mechanisms
- Operating modes and state transitions
- System adaptation and learning capabilities

### Configuration

The system can be configured through:

1. **Base Configuration** (`models/config.py`):
   - Generator parameters
   - Collection settings
   - Treatment facility specifications
   - Monitoring intervals
   - Visualization preferences

2. **State Definitions** (`models/state.py`):
   - System state specifications
   - Transition rules
   - State-dependent behaviors
   - Performance thresholds

3. **Data Structures** (`models/data_classes.py`):
   - Core data models
   - Performance metrics
   - System statistics
   - Event definitions

## Performance Metrics

The system tracks and analyzes:

1. **Storage Efficiency**:
   - Utilization rates
   - Capacity adjustments
   - Overflow prevention

2. **Treatment Efficiency**:
   - Conversion rates
   - Energy consumption
   - Processing times

3. **System Performance**:
   - Demand satisfaction
   - Collection efficiency
   - Environmental impact
   - Resource utilization
