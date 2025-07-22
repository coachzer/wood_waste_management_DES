# Discrete Event Wood Waste Management Simulation

A Python-based simulation system for modeling and optimizing wood waste management operations, featuring stochastic optimization and monitoring capabilities.

## Project Structure

```text
├── config/                 # Configuration modules
│   ├── base_config.py     # Base simulation parameters
│   ├── cost_config.py     # Cost-related configurations
│   └── facility_config.py # Facility-specific settings
├── core/                  # Core simulation components
│   ├── collection_coordinator.py # Collection coordination
│   ├── collector.py       # Waste collection simulation
│   ├── collector_utils.py # Collection utilities
│   ├── cost_tracker.py    # Cost tracking system
│   ├── facility_builder.py # Facility initialization
│   ├── generator.py       # Waste generation simulation
│   ├── generator_utils.py # Generation utilities
│   ├── overflow.py        # Overflow handling
│   ├── simulation_manager.py # Core simulation orchestration
│   ├── storage_manager.py # Storage management
│   ├── treatment.py       # Treatment facility simulation
│   └── treatment_utils.py # Treatment utilities
├── data/                  # Data files
│   ├── demand.json        # Demand specifications
│   └── regions/           # Regional data
├── models/                # Data models
│   ├── data_classes.py    # Core data structures
│   ├── distances.py       # Distance calculations
│   ├── enums.py          # Enumeration definitions
│   ├── facility_data.py   # Facility data management
│   ├── regional_tracker.py # Regional statistics
│   └── state.py          # System state management
├── monitoring/            # Monitoring and visualization
│   ├── data_collector.py  # Data collection
│   ├── metrics_analyzer.py # Metrics analysis
│   ├── mfa_visualization.py # Material flow analysis
│   ├── monitor.py         # System monitoring
│   ├── system_monitor.py  # Overall system monitoring
│   └── visualizations/    # Visualization modules
│       ├── efficiency_plots.py
│       ├── production_plots.py
│       ├── regional_waste_plots.py
│       ├── storage_plots.py
│       ├── system_plots.py
│       └── waste_plots.py
└── optimization/          # Optimization system
    ├── entity_params.py   # Entity parameters
    ├── objectives/        # Optimization objectives
    │   ├── collection.py  # Collection optimization
    │   ├── cost.py       # Cost optimization
    │   ├── overflow.py    # Overflow prevention
    │   ├── storage.py     # Storage optimization
    │   └── treatment.py   # Treatment optimization
    ├── uncertainty/       # Uncertainty handling
    │   ├── base.py       # Base uncertainty
    │   ├── optimization.py # Uncertainty optimization
    │   └── scenarios.py   # Scenario generation
    └── utils/             # Optimization utilities
        └── simulation_tracker.py # Simulation tracking
```

## Project Components

### Entry Point (main.py)

The main entry point of the simulation system, responsible for:

- Initializing the simulation manager
- Setting up baseline uncertainty parameters
- Configuring optimization components
- Running the simulation process
- Generating visualizations

### Core Components

#### Simulation Manager

The `SimulationManager` (core/simulation_manager.py) orchestrates the entire simulation:

- Environment setup and initialization
- Entity management (generators, collectors, operators)
- Optimization process coordination
- System state monitoring
- Performance tracking and visualization
- Results analysis and reporting

## Dependencies

Core dependencies:

- simpy>=4.0.1 (Discrete Event Simulation)
- matplotlib>=3.5.0 (Visualization)
- seaborn>=0.11.2 (Enhanced visualizations)
- pandas>=1.3.0 (Data handling)
- numpy>=1.21.0 (Numerical operations)

## Installation & Setup

1. Clone the repository
2. Create a virtual environment:

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:

```bash
pip install -r requirements.txt
```

4. Configure the simulation:
   - Adjust simulation parameters in `config/base_config.py`
   - Set cost parameters in `config/cost_config.py`
   - Configure facilities in `config/facility_config.py`
   - Modify regional settings in `data/regions/`

5. Run the simulation:

```bash
python main.py
```

## Key Features

### Advanced Simulation System

- **Multi-Year Simulation**
  - Dynamic parameter adjustment across years
  - Automatic efficiency scaling
  - Progressive demand adjustments

- **Stochastic Optimization**
  - Risk-aware objective evaluation
  - Scenario-based optimization
  - Robust decision making with uncertainty

- **Regional Management**
  - Region-specific configurations
  - Local demand handling
  - Regional performance tracking

### Simulation Components

#### Waste Generation

- Multiple waste type support
- Dynamic generation rates
- Seasonal variations
- Storage management
- Priority-based scheduling

#### Collection System

- Multiple collection strategies:
  - Collaborative: Region-based coordination
  - Competitive: Priority-based independent operation
- Dynamic routing
- Cost optimization
- Performance monitoring
- Demand-based scheduling

#### Treatment Processing

- **Waste-specific Transformations**
  - Quality-dependent conversion rates
  - Material quality assessment
  - Furniture material grading
  - Efficiency variations by type
- **Process Management**
  - Dynamic capacity adjustment
  - Equipment failure handling
  - Automated recovery procedures
  - Batch optimization
- **Resource Tracking**
  - Energy consumption monitoring
  - Processing cost calculation
  - Utilization metrics
  - Performance analysis
- **Demand Fulfillment**
  - Priority-based processing
  - Quality-driven output
  - Target tracking
  - Efficiency optimization

### Monitoring & Visualization

- **Real-time Monitoring**
  - Generation Metrics:
    - Volume by waste type
    - Temporal patterns
    - Regional distribution
  - Collection Analysis:
    - Transport efficiency
    - Route optimization
    - Vehicle utilization
  - Cost Tracking:
    - Processing costs
    - Transportation costs
    - Storage costs
    - Landfill costs
  - Performance Metrics:
    - Storage utilization
    - Processing efficiency
    - Equipment reliability
    - Environmental impact

- **Visualization Types**
  - Efficiency analysis
  - Production tracking
  - Regional waste distribution
  - Storage utilization
  - System performance
  - Material flow analysis

### Optimization Framework

- **Multi-objective Optimization**
  - Storage Utilization: Optimizes storage capacity usage across facilities
  - Collection Efficiency: Maximizes waste collection performance and routing
  - Treatment Efficiency: Optimizes processing rates and resource utilization
  - Cost Optimization: Minimizes operational costs while maintaining performance
  - Overflow Prevention: Penalizes and prevents storage capacity violations
  - Environmental Impact: Tracks and reduces environmental footprint

- **Risk-Aware Decision Making**
  - Scenario Generation: Creates diverse operational scenarios
  - Uncertainty Handling: Manages variability in:
    - Waste generation rates
    - Collection times
    - Treatment efficiency
    - Equipment reliability
  - Risk Measures: Calculates:
    - Value at Risk (VaR)
    - Operation confidence levels
    - Reliability metrics
  - Robustness Analysis: Ensures solutions perform well across scenarios

- **Performance Tracking**
  - Metrics:
    - Processing scores
    - Storage utilization
    - Energy efficiency
    - Environmental impact
    - Cost breakdown
  - Historical Analysis:
    - Trend analysis
    - Performance patterns
    - Efficiency evolution
  - Real-time Monitoring:
    - Current state evaluation
    - Risk level assessment
    - Optimization progress

## Simulation States

### Storage Management

- Normal: 30-85% utilization
- Near-Capacity: >85% utilization
- Under-Utilization: <30% utilization

### Processing States

- High-Volume: >80% capacity
- Standard: 20-80% capacity
- Low-Volume: <20% capacity

### Results & Analysis

The simulation generates comprehensive results in:

- `plots/`: Visualization outputs
- `results/`: Simulation history and metrics
