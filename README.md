# Discrete Event Wood Waste Management Simulation

A Python-based simulation system for modeling and optimizing industrial waste management operations. The system simulates waste generation, collection, and treatment processes while providing comprehensive monitoring and optimization capabilities.

## Installation & Usage

1. Install required dependencies:

```bash
pip install -r requirements.txt
```

2. Run the simulation:

```bash
python main.py
```

The system will generate visualizations and metrics in the `plots/` directory.

## Features

### Core Components

- **Waste Generation**: Simulates multiple waste generators with:
  - Configurable waste types (sawdust, wood cuttings, bark, etc.)
  - Dynamic generation rates with state-based behavior
  - Advanced storage capacity management
  - Priority-based collection scheduling
  - State-driven operational adjustments

- **Waste Collection**: Models collection operations with:
  - Multiple collection strategies (competitive/collaborative)
  - Regional-based collection routing 
  - Transport cost optimization
  - Collection efficiency tracking
  - Dynamic demand-based scheduling

- **Treatment Processing**: Simulates treatment facilities with:
  - Waste-specific transformation processes
  - State-of-the-art storage management
  - Processing capacity constraints
  - Energy consumption tracking
  - Efficiency-based conversion rates

### System States & Behavior

- **Storage States**:
  - Normal Operation (30-85% utilization)
  - Near-Capacity Operations (>85%)
  - Under-Utilization Handling (<30%)

- **Operating Modes**:
  - Fixed Parameter Mode: Static capacity and rates
  - Dynamic Parameter Mode: Adaptive capacity and variable rates

- **Treatment States**:
  - High-Volume Processing
  - Standard Processing
  - Low-Volume Processing

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

### Optimization

- Automated system optimization considering:
  - Storage utilization
  - Collection efficiency
  - Treatment efficiency
  - Environmental impact
  - Energy consumption
  - Resource utilization

## Documentation

Detailed documentation is available in the `docs/` directory:

- **Behavior Model**: Comprehensive documentation of system states, transitions, and behaviors (`docs/behavior_model.md`)
  - Storage behavior models
  - Treatment process models
  - Inventory management
  - Production control
  - Operating modes

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
