import plotly.graph_objects as go
import plotly.subplots as sp
import pandas as pd
import numpy as np
from typing import Dict, List
import os

class ScenarioComparison:    
    def __init__(self, results: List[Dict]):
        self.results = results
        self.output_dir = "plots/scenario_comparison"
        os.makedirs(self.output_dir, exist_ok=True)
    
    def create_storage_heatmaps(self):
        """Create heatmap visualizations of storage utilization over time for all scenarios"""
        # Generation and collection remain as before
        for entity_type in ['generation', 'collection']:
            self._create_entity_storage_heatmap(entity_type)

        self._create_processing_storage_heatmap('waste')
        self._create_processing_storage_heatmap('product')
        self._create_processing_storage_heatmap('product_to_sell')

    def _create_processing_storage_heatmap(self, storage_type: str):
        """Create heatmap for a specific processor storage type"""
        fig = sp.make_subplots(
            rows=len(self.results), cols=1,
            subplot_titles=[f"{r['scenario_name']} ({r['inventory_policy']}, {r['stock_strategy']})" for r in self.results],
            vertical_spacing=0.02
        )
        for idx, result in enumerate(self.results, 1):
            monitor = result['monitor']
            history = monitor.data_collector.get_processing_history()
            match storage_type:
                case 'waste':
                    heatmap_data = self._extract_processor_waste_storage_data(history)
                    title = "Waste Storage Utilization (%)"
                case 'product':
                    heatmap_data = self._extract_processor_product_storage_data(history)
                    title = "Product Storage Utilization (%)"
                case 'product_to_sell':
                    heatmap_data = self._extract_processor_product_to_sell_storage_data(history)
                    title = "Product-to-Sell Storage Utilization (%)"

            if heatmap_data['z_values']:
                fig.add_trace(
                    go.Heatmap(
                        z=heatmap_data['z_values'],
                        x=heatmap_data['x_values'],
                        y=heatmap_data['y_values'],
                        colorscale='RdYlBu_r',
                        zmin=0, zmax=100,
                        showscale=(idx == 1),
                        colorbar={"title": title, "x": 1.02} if idx == 1 else None
                    ),
                    row=idx, col=1
                )
        fig.update_layout(
            title=f"Processing {title} Heatmap - All Scenarios",
            height=200 * len(self.results),
            showlegend=False
        )
        fig.update_xaxes(title_text="Time")
        fig.update_yaxes(title_text="Processor")
        fig.write_html(f"{self.output_dir}/processing_{storage_type}_storage_heatmap.html")

    def _extract_processor_waste_storage_data(self, history: Dict) -> Dict:
        """Extract waste storage utilization for processors"""
        entities = list(history.keys())
        if not entities:
            return {'x_values': [], 'y_values': [], 'z_values': []}
        all_timestamps = []
        for entity_data in history.values():
            if 'timestamps' in entity_data:
                all_timestamps.extend(entity_data['timestamps'])
        if not all_timestamps:
            return {'x_values': [], 'y_values': [], 'z_values': []}
        time_range = np.linspace(min(all_timestamps), max(all_timestamps), 50)
        z_matrix = []
        for entity in entities:
            entity_data = history[entity]
            # Waste storage utilization: entity_data['storage']['waste_utilization']
            if 'storage' in entity_data and 'waste_utilization' in entity_data['storage']:
                timestamps = entity_data['timestamps']
                utilization = entity_data['storage']['waste_utilization']
                if utilization:
                    interpolated = np.interp(time_range, timestamps, utilization)
                    z_matrix.append(interpolated)
                else:
                    z_matrix.append(np.zeros(len(time_range)))
            else:
                z_matrix.append(np.zeros(len(time_range)))
        return {
            'x_values': time_range,
            'y_values': entities,
            'z_values': z_matrix
        }

    def _extract_processor_product_storage_data(self, history: Dict) -> Dict:
        """Extract product storage utilization for processors"""
        entities = list(history.keys())
        if not entities:
            return {'x_values': [], 'y_values': [], 'z_values': []}
        all_timestamps = []
        for entity_data in history.values():
            if 'timestamps' in entity_data:
                all_timestamps.extend(entity_data['timestamps'])
        if not all_timestamps:
            return {'x_values': [], 'y_values': [], 'z_values': []}
        time_range = np.linspace(min(all_timestamps), max(all_timestamps), 50)
        z_matrix = []
        for entity in entities:
            entity_data = history[entity]
            # Product storage utilization: entity_data['storage']['product_utilization']
            if 'storage' in entity_data and 'product_utilization' in entity_data['storage']:
                timestamps = entity_data['timestamps']
                utilization = entity_data['storage']['product_utilization']
                if utilization:
                    interpolated = np.interp(time_range, timestamps, utilization)
                    z_matrix.append(interpolated)
                else:
                    z_matrix.append(np.zeros(len(time_range)))
            else:
                z_matrix.append(np.zeros(len(time_range)))
        return {
            'x_values': time_range,
            'y_values': entities,
            'z_values': z_matrix
        }

    def _extract_processor_product_to_sell_storage_data(self, history: Dict) -> Dict:
        """Extract product-to-sell storage utilization for processors"""
        entities = list(history.keys())
        if not entities:
            return {'x_values': [], 'y_values': [], 'z_values': []}
        all_timestamps = []
        for entity_data in history.values():
            if 'timestamps' in entity_data:
                all_timestamps.extend(entity_data['timestamps'])
        if not all_timestamps:
            return {'x_values': [], 'y_values': [], 'z_values': []}
        time_range = np.linspace(min(all_timestamps), max(all_timestamps), 50)
        z_matrix = []
        for entity in entities:
            entity_data = history[entity]
            # Product-to-sell storage utilization: entity_data['storage']['product_to_sell_utilization']
            if 'storage' in entity_data and 'product_to_sell_utilization' in entity_data['storage']:
                timestamps = entity_data['timestamps']
                utilization = entity_data['storage']['product_to_sell_utilization']
                if utilization:
                    interpolated = np.interp(time_range, timestamps, utilization)
                    z_matrix.append(interpolated)
                else:
                    z_matrix.append(np.zeros(len(time_range)))
            else:
                z_matrix.append(np.zeros(len(time_range)))
        return {
            'x_values': time_range,
            'y_values': entities,
            'z_values': z_matrix
        }
    
    def _create_entity_storage_heatmap(self, entity_type: str):
        """Create storage heatmap for specific entity type"""
        
        fig = sp.make_subplots(
            rows=len(self.results), cols=1,
            subplot_titles=[f"{r['scenario_name']} ({r['inventory_policy']}, {r['stock_strategy']})" 
                          for r in self.results],
            vertical_spacing=0.02
        )
        
        for idx, result in enumerate(self.results, 1):
            monitor = result['monitor']
            
            if entity_type == 'generation':
                history = monitor.data_collector.get_generation_history()
                heatmap_data = self._extract_storage_data(history, 'storage_utilization')
            elif entity_type == 'collection':
                history = monitor.data_collector.get_collection_history()
                heatmap_data = self._extract_collection_storage_data(history)
            else:  # processing
                history = monitor.data_collector.get_processing_history()
                heatmap_data = self._extract_processing_storage_data(history)
            
            if heatmap_data['z_values']:
                fig.add_trace(
                    go.Heatmap(
                        z=heatmap_data['z_values'],
                        x=heatmap_data['x_values'],
                        y=heatmap_data['y_values'],
                        colorscale='RdYlBu_r',
                        zmin=0, zmax=100,
                        showscale=(idx == 1),
                        colorbar={"title": "Storage Utilization (%)", "x": 1.02} if idx == 1 else None
                    ),
                    row=idx, col=1
                )
        
        fig.update_layout(
            title=f"{entity_type.title()} Storage Utilization Heatmap - All Scenarios",
            height=200 * len(self.results),
            showlegend=False
        )
        
        fig.update_xaxes(title_text="Time")
        fig.update_yaxes(title_text="Entity")
        
        fig.write_html(f"{self.output_dir}/{entity_type}_storage_heatmap.html")
    
    def _extract_storage_data(self, history: Dict, metric: str) -> Dict:
        """Extract storage utilization data for heatmap"""
        entities = list(history.keys())
        if not entities:
            return {'x_values': [], 'y_values': [], 'z_values': []}
        
        all_timestamps = []
        for entity_data in history.values():
            if 'timestamps' in entity_data:
                all_timestamps.extend(entity_data['timestamps'])
        
        if not all_timestamps:
            return {'x_values': [], 'y_values': [], 'z_values': []}
        
        time_range = np.linspace(min(all_timestamps), max(all_timestamps), 50)
        z_matrix = []
        
        for entity in entities:
            entity_data = history[entity]
            if metric in entity_data and entity_data[metric]:
                timestamps = entity_data['timestamps']
                values = entity_data[metric]
                interpolated = np.interp(time_range, timestamps, values)
                z_matrix.append(interpolated)
            else:
                z_matrix.append(np.zeros(len(time_range)))
        
        return {
            'x_values': time_range,
            'y_values': entities,
            'z_values': z_matrix
        }
    
    def _extract_collection_storage_data(self, history: Dict) -> Dict:
        """Extract collection center storage data"""
        entities = list(history.keys())
        if not entities:
            return {'x_values': [], 'y_values': [], 'z_values': []}
        
        all_timestamps = []
        for entity_data in history.values():
            if 'timestamps' in entity_data:
                all_timestamps.extend(entity_data['timestamps'])
        
        if not all_timestamps:
            return {'x_values': [], 'y_values': [], 'z_values': []}
        
        time_range = np.linspace(min(all_timestamps), max(all_timestamps), 50)
        z_matrix = []
        
        for entity in entities:
            entity_data = history[entity]
            if 'collected_volumes' in entity_data:
                timestamps = entity_data['timestamps']
                total_volumes = []
                for _ in timestamps:
                    total = sum(sum(volumes) if isinstance(volumes, list) else volumes 
                              for volumes in entity_data['collected_volumes'].values())
                    total_volumes.append(min(total / 1000 * 100, 100))  # Normalize to percentage
                
                if total_volumes:
                    interpolated = np.interp(time_range, timestamps, total_volumes)
                    z_matrix.append(interpolated)
                else:
                    z_matrix.append(np.zeros(len(time_range)))
            else:
                z_matrix.append(np.zeros(len(time_range)))
        
        return {
            'x_values': time_range,
            'y_values': entities,
            'z_values': z_matrix
        }
    
    def _extract_processing_storage_data(self, history: Dict) -> Dict:
        """Extract processing facility storage data"""
        entities = list(history.keys())
        if not entities:
            return {'x_values': [], 'y_values': [], 'z_values': []}
        
        all_timestamps = []
        for entity_data in history.values():
            if 'timestamps' in entity_data:
                all_timestamps.extend(entity_data['timestamps'])
        
        if not all_timestamps:
            return {'x_values': [], 'y_values': [], 'z_values': []}
        
        time_range = np.linspace(min(all_timestamps), max(all_timestamps), 50)
        z_matrix = []
        
        for entity in entities:
            entity_data = history[entity]
            if 'storage' in entity_data and 'utilization' in entity_data['storage']:
                timestamps = entity_data['timestamps']
                utilization = entity_data['storage']['utilization']
                
                if utilization:
                    interpolated = np.interp(time_range, timestamps, utilization)
                    z_matrix.append(interpolated)
                else:
                    z_matrix.append(np.zeros(len(time_range)))
            else:
                z_matrix.append(np.zeros(len(time_range)))
        
        return {
            'x_values': time_range,
            'y_values': entities,
            'z_values': z_matrix
        }
    
    def create_temporal_comparison(self):
        """Create time-series comparison plots for key metrics"""
        
        self._create_generation_comparison()
        self._create_collection_comparison()
        self._create_processing_comparison()
        self._create_cost_comparison()
        self._create_overflow_comparison()
    
    def _create_generation_comparison(self):
        """Compare waste generation across scenarios over time"""
        fig = go.Figure()
        
        for result in self.results:
            monitor = result['monitor']
            history = monitor.data_collector.get_generation_history()
            
            total_generation = self._aggregate_generation_data(history)
            if total_generation['timestamps']:
                fig.add_trace(go.Scatter(
                    x=total_generation['timestamps'],
                    y=total_generation['volumes'],
                    mode='lines',
                    name=f"{result['inventory_policy']} | {result['stock_strategy']}",
                    line={'width': 2}
                ))
        
        fig.update_layout(
            title="Total Waste Generation Over Time - Scenario Comparison",
            xaxis_title="Time",
            yaxis_title="Cumulative Volume (m³)",
            hovermode='x unified'
        )
        
        fig.write_html(f"{self.output_dir}/generation_comparison.html")
    
    def _aggregate_generation_data(self, history: Dict) -> Dict:
        """Aggregate generation data across all generators"""
        all_timestamps = set()
        all_data = {}
        
        for data in history.values():
            timestamps = data.get('timestamps', [])
            for _, totals in data.get('total_generated', {}).items():
                if len(timestamps) == len(totals):
                    for t, v in zip(timestamps, totals):
                        all_timestamps.add(t)
                        if t not in all_data:
                            all_data[t] = 0
                        all_data[t] += v
        
        sorted_times = sorted(all_timestamps)
        return {
            'timestamps': sorted_times,
            'volumes': [all_data[t] for t in sorted_times]
        }
    
    def _create_collection_comparison(self):
        """Compare collection efficiency across scenarios"""
        fig = go.Figure()
        
        for result in self.results:
            monitor = result['monitor']
            history = monitor.data_collector.get_collection_history()
            
            avg_efficiency = self._calculate_average_efficiency(history)
            if avg_efficiency['timestamps']:
                fig.add_trace(go.Scatter(
                    x=avg_efficiency['timestamps'],
                    y=avg_efficiency['efficiency'],
                    mode='lines',
                    name=f"{result['inventory_policy']} | {result['stock_strategy']}",
                    line={'width': 2}
                ))
        
        fig.update_layout(
            title="Collection Efficiency Over Time - Scenario Comparison",
            xaxis_title="Time",
            yaxis_title="Average Efficiency",
            hovermode='x unified'
        )
        
        fig.write_html(f"{self.output_dir}/collection_comparison.html")
    
    def _calculate_average_efficiency(self, history: Dict) -> Dict:
        """Calculate average collection efficiency over time"""
        time_efficiency = {}
        for _, data in history.items():
            timestamps = data.get('timestamps', [])
            efficiency = data.get('efficiency', [])
            for t, e in zip(timestamps, efficiency):
                if t not in time_efficiency:
                    time_efficiency[t] = []
                time_efficiency[t].append(e)
        sorted_times = sorted(time_efficiency.keys())
        avg_efficiency = [np.mean(time_efficiency[t]) for t in sorted_times]
        return {
            'timestamps': sorted_times,
            'efficiency': avg_efficiency
        }
    
    def _create_processing_comparison(self):
        """Compare processing throughput across scenarios"""
        fig = go.Figure()
        
        for result in self.results:
            monitor = result['monitor']
            history = monitor.data_collector.get_processing_history()
            
            throughput = self._calculate_processing_throughput(history)
            if throughput['timestamps']:
                fig.add_trace(go.Scatter(
                    x=throughput['timestamps'],
                    y=throughput['processed'],
                    mode='lines',
                    name=f"{result['inventory_policy']} | {result['stock_strategy']}",
                    line={'width': 2}
                ))
        
        fig.update_layout(
            title="Processing Throughput Over Time - Scenario Comparison",
            xaxis_title="Time",
            yaxis_title="Cumulative Processed Volume (m³)",
            hovermode='x unified'
        )
        
        fig.write_html(f"{self.output_dir}/processing_comparison.html")
    
    def _calculate_processing_throughput(self, history: Dict) -> Dict:
        """Calculate cumulative processing throughput"""
        time_throughput = {}
        for _, data in history.items():
            timestamps = data.get('timestamps', [])
            processed_total = data.get('processed', {}).get('total', [])
            for t, p in zip(timestamps, processed_total):
                if t not in time_throughput:
                    time_throughput[t] = 0
                time_throughput[t] += p
        sorted_times = sorted(time_throughput.keys())
        cumulative = 0
        cumulative_processed = []
        for t in sorted_times:
            cumulative += time_throughput[t]
            cumulative_processed.append(cumulative)
        return {
            'timestamps': sorted_times,
            'processed': cumulative_processed
        }
    
    def _create_cost_comparison(self):
        """Compare total costs across scenarios"""
        fig = go.Figure()
        
        for result in self.results:
            monitor = result['monitor']
            cost_history = monitor.data_collector.cost_history
            
            if cost_history['timestamps']:
                total_costs = []
                for i, _ in enumerate(cost_history['timestamps']):
                    total_cost = 0
                    if i < len(cost_history['energy']):
                        total_cost += cost_history['energy'][i]
                    if i < len(cost_history['processing']):
                        total_cost += cost_history['processing'][i]
                    if i < len(cost_history['transport']):
                        total_cost += cost_history['transport'][i]
                    total_costs.append(total_cost)
                
                fig.add_trace(go.Scatter(
                    x=cost_history['timestamps'],
                    y=np.cumsum(total_costs),
                    mode='lines',
                    name=f"{result['inventory_policy']} | {result['stock_strategy']}",
                    line={'width': 2}
                ))
        
        fig.update_layout(
            title="Cumulative Costs Over Time - Scenario Comparison",
            xaxis_title="Time",
            yaxis_title="Cumulative Cost",
            hovermode='x unified'
        )
        
        fig.write_html(f"{self.output_dir}/cost_comparison.html")
    
    def _create_overflow_comparison(self):
        """Compare overflow events across scenarios"""
        fig = sp.make_subplots(
            rows=2, cols=2,
            subplot_titles=['Generator Overflow', 'Collector Overflow', 
                          'Treatment Overflow', 'Total Overflow Cost'],
            vertical_spacing=0.1
        )
        
        overflow_types = [
            ('generator_overflow', 1, 1),
            ('collector_overflow', 1, 2),
            ('treatment_overflow', 2, 1),
            ('total_cost', 2, 2)
        ]
        
        for result in self.results:
            monitor = result['monitor']
            overflow_history = monitor.data_collector.overflow_history
            label = f"{result['inventory_policy']} | {result['stock_strategy']}"
            
            for overflow_type, row, col in overflow_types:
                if overflow_type in overflow_history:
                    data = overflow_history[overflow_type]
                    fig.add_trace(
                        go.Scatter(
                            x=data['timestamps'],
                            y=data['values'],
                            mode='lines',
                            name=label,
                            showlegend=(row == 1 and col == 1),
                            line={'width': 2}
                        ),
                        row=row, col=col
                    )
        
        fig.update_layout(
            title="Overflow Events Comparison Across Scenarios",
            height=600
        )
        
        fig.write_html(f"{self.output_dir}/overflow_comparison.html")

    def create_cost_impact_comparison(self):
        """Create bar charts comparing cost and environmental impact breakdowns across scenarios"""
        cost_components = ['energy', 'processing', 'transport', 'overflow']
        impact_components = ['emissions', 'resource_use']  # Add more if tracked
        scenario_labels = []
        cost_data = {comp: [] for comp in cost_components}
        impact_data = {comp: [] for comp in impact_components}

        for result in self.results:
            monitor = result['monitor']
            scenario_labels.append(f"{result['inventory_policy']} | {result['stock_strategy']}")
            cost_history = monitor.data_collector.cost_history
            overflow_history = monitor.data_collector.overflow_history

            # Extract final values for each cost component
            cost_data['energy'].append(np.sum(cost_history.get('energy', [])))
            cost_data['processing'].append(np.sum(cost_history.get('processing', [])))
            cost_data['transport'].append(np.sum(cost_history.get('transport', [])))
            cost_data['overflow'].append(overflow_history.get('total_cost', {}).get('values', [0])[-1] if overflow_history.get('total_cost', {}).get('values') else 0)

            # Environmental impact extraction (example: emissions, resource use)
            # If you track these in data_collector, extract similarly
            impact_data['emissions'].append(getattr(monitor.data_collector, 'total_emissions', 0))
            impact_data['resource_use'].append(getattr(monitor.data_collector, 'total_resource_use', 0))

        # Bar chart for cost breakdown
        fig_cost = go.Figure()
        for comp in cost_components:
            fig_cost.add_trace(go.Bar(x=scenario_labels, y=cost_data[comp], name=comp.title()))
        fig_cost.update_layout(title="Cost Breakdown by Scenario", barmode='stack', xaxis_title="Scenario", yaxis_title="Total Cost")
        fig_cost.write_html(f"{self.output_dir}/cost_breakdown_comparison.html")

        # Bar chart for environmental impact breakdown
        fig_impact = go.Figure()
        for comp in impact_components:
            fig_impact.add_trace(go.Bar(x=scenario_labels, y=impact_data[comp], name=comp.title()))
        fig_impact.update_layout(title="Environmental Impact Breakdown by Scenario", barmode='stack', xaxis_title="Scenario", yaxis_title="Impact")
        fig_impact.write_html(f"{self.output_dir}/impact_breakdown_comparison.html")

    def create_pareto_front_plot(self):
        """Create a 2D scatter plot of cost vs. environmental impact, highlighting Pareto front"""
        scenario_labels = []
        total_costs = []
        total_impacts = []

        for result in self.results:
            monitor = result['monitor']
            scenario_labels.append(f"{result['inventory_policy']} | {result['stock_strategy']}")
            cost_history = monitor.data_collector.cost_history
            overflow_history = monitor.data_collector.overflow_history
            total_cost = np.sum(cost_history.get('energy', [])) + np.sum(cost_history.get('processing', [])) + np.sum(cost_history.get('transport', []))
            total_cost += overflow_history.get('total_cost', {}).get('values', [0])[-1] if overflow_history.get('total_cost', {}).get('values') else 0
            total_impact = getattr(monitor.data_collector, 'total_emissions', 0)  # Replace with actual impact metric
            total_costs.append(total_cost)
            total_impacts.append(total_impact)

        # Pareto front calculation
        points = np.array(list(zip(total_costs, total_impacts)))
        pareto_mask = self._find_pareto_front(points)

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=total_costs,
            y=total_impacts,
            mode='markers+text',
            text=scenario_labels,
            textposition='top center',
            marker={"size": 12, "color": ['red' if is_pareto else 'gray' for is_pareto in pareto_mask]},
            name='Scenarios'
        ))
        fig.update_layout(title="Scenario Pareto Front: Cost vs. Environmental Impact", xaxis_title="Total Cost", yaxis_title="Total Environmental Impact")
        fig.write_html(f"{self.output_dir}/pareto_front.html")

    def _find_pareto_front(self, points):
        """Return a boolean mask for Pareto front points (minimize both objectives)"""
        is_pareto = np.ones(points.shape[0], dtype=bool)
        for i, point in enumerate(points):
            if is_pareto[i]:
                is_pareto[is_pareto] = np.any(points[is_pareto] < point, axis=1)
                is_pareto[i] = True  
        return is_pareto

    def create_summary_dashboard(self):
        """Create a comprehensive dashboard with key metrics"""

        def safe_get_nested_value(data, path, default=0):
            """Safely navigate nested dictionary structure"""
            try:
                result = data
                for key in path:
                    if isinstance(result, dict) and key in result:
                        result = result[key]
                    elif isinstance(result, list) and isinstance(key, int) and key < len(result):
                        result = result[key]
                    else:
                        return default
                return result if result is not None else default
            except (KeyError, TypeError, IndexError):
                return default

        def get_total_generated(generation_history):
            """Calculate total waste generated - use final cumulative values only"""
            total = 0
            print("\n--- Generation Analysis ---")
            
            for entity_id, data in generation_history.items():
                entity_total = 0
                total_generated = safe_get_nested_value(data, ['total_generated'], {})
                
                if isinstance(total_generated, dict):
                    for waste_type, values in total_generated.items():
                        if isinstance(values, list) and values:
                            # Take only the FINAL cumulative value
                            final_value = values[-1]
                            entity_total += final_value
                            print(f"  Entity {entity_id}, Type {waste_type}: {final_value:.2f}")
                        elif isinstance(values, (int, float)):
                            entity_total += values
                            print(f"  Entity {entity_id}, Type {waste_type}: {values:.2f}")
                
                total += entity_total
                print(f"  Entity {entity_id} total: {entity_total:.2f}")
            
            print(f"Total Generated: {total:.2f}")
            return total
        
        def get_total_collected(collection_history: Dict) -> Dict:
            """Calculate collector volumes"""
            collector_volumes = {}
            for collector, history in collection_history.items():
                total = 0
                for _, volumes in history.get("collected_volumes", {}).items():
                    if volumes:
                        total += volumes[-1] if volumes else 0 
                collector_volumes[collector] = total
            return collector_volumes
        
        def get_total_processed(processing_history):
            """Calculate total waste processed"""
            total = 0
            print("\n--- Processing Analysis ---")
            
            for entity_id, data in processing_history.items():
                entity_total = 0
                
                # Try different possible data structures
                processed_data = safe_get_nested_value(data, ['processed'], {})
                
                if isinstance(processed_data, dict):
                    # Try 'total' field first
                    processed_total = safe_get_nested_value(processed_data, ['total'], [])
                    if isinstance(processed_total, list) and processed_total:
                        entity_total = processed_total[-1]  # Final cumulative value
                    elif isinstance(processed_total, (int, float)):
                        entity_total = processed_total
                    else:
                        # Sum all waste types if 'total' not available
                        for waste_type, values in processed_data.items():
                            if isinstance(values, list) and values:
                                entity_total += values[-1]
                            elif isinstance(values, (int, float)):
                                entity_total += values
                
                total += entity_total
                print(f"  Entity {entity_id} total: {entity_total:.2f}")
            
            print(f"Total Processed: {total:.2f}")
            return total

        def get_total_overflow_cost(overflow_history):
            """Get total overflow cost"""
            total_cost_data = safe_get_nested_value(overflow_history, ['total_cost', 'values'], [])
            if isinstance(total_cost_data, list) and total_cost_data:
                return total_cost_data[-1]
            elif isinstance(total_cost_data, (int, float)):
                return total_cost_data
            return 0

        def get_efficiency_metrics(monitor):
            """Get efficiency metrics from the metrics analyzer"""
            try:
                generation_history = monitor.data_collector.get_generation_history()
                collection_history = monitor.data_collector.get_collection_history()
                processing_history = monitor.data_collector.get_processing_history()
                
                # Use the existing metrics analyzer if available
                if hasattr(monitor, 'metrics_analyzer'):
                    efficiency_metrics = monitor.metrics_analyzer.calculate_efficiency_metrics(
                        generation_history, collection_history, processing_history
                    )
                    return efficiency_metrics
                return {}
            except Exception as e:
                print(f"Warning: Could not calculate efficiency metrics: {e}")
                return {}
            
        def debug_data_structure(history_data, data_type):
            """Debug function to understand data structure"""
            print(f"\n=== DEBUG: {data_type} Data Structure ===")
            for entity_id, data in list(history_data.items())[:2]:  # Show first 2 entities
                print(f"Entity {entity_id}:")
                print(f"  Keys: {list(data.keys())}")
                for key, value in data.items():
                    if isinstance(value, dict):
                        print(f"  {key}: dict with keys {list(value.keys())}")
                        # Show sample values
                        for sub_key, sub_value in list(value.items())[:2]:
                            if isinstance(sub_value, list):
                                print(f"    {sub_key}: list of length {len(sub_value)}, sample: {sub_value[:3] if len(sub_value) >= 3 else sub_value}")
                            else:
                                print(f"    {sub_key}: {type(sub_value).__name__} = {sub_value}")
                    elif isinstance(value, list):
                        print(f"  {key}: list of length {len(value)}, sample: {value[:3] if len(value) >= 3 else value}")
                    else:
                        print(f"  {key}: {type(value).__name__} = {value}")
            print("=" * 50)

        # Calculate metrics for each scenario
        metrics_data = []
        
        for result in self.results:
            monitor = result['monitor']
            generation_history = monitor.data_collector.get_generation_history()
            collection_history = monitor.data_collector.get_collection_history()
            processing_history = monitor.data_collector.get_processing_history()
            overflow_history = monitor.data_collector.overflow_history

            print(f"\n{'='*60}")
            print(f"SCENARIO: {result['scenario_name']}")
            print(f"Policy: {result['inventory_policy']}, Strategy: {result['stock_strategy']}")
            print(f"{'='*60}")

            # Debug data structures
            debug_data_structure(generation_history, "Generation")
            debug_data_structure(collection_history, "Collection") 
            debug_data_structure(processing_history, "Processing")

            # Calculate totals using fixed helper functions
            total_generated = get_total_generated(generation_history)
            total_collected = sum(get_total_collected(collection_history).values())
            total_processed = get_total_processed(processing_history)

            # Calculate overflow cost
            total_overflow_cost = 0
            if 'total_cost' in overflow_history and 'values' in overflow_history['total_cost']:
                cost_values = overflow_history['total_cost']['values']
                if cost_values:
                    total_overflow_cost = cost_values[-1]

            # Calculate realistic efficiency percentages
            collection_eff = (total_collected / total_generated * 100) if total_generated > 0 else 0
            processing_eff = (total_processed / total_collected * 100) if total_collected > 0 else 0

            print("\n--- FINAL METRICS ---")
            print(f"Total Generated: {total_generated:.2f} m³")
            print(f"Total Collected: {total_collected:.2f} m³") 
            print(f"Total Processed: {total_processed:.2f} m³")
            print(f"Collection Efficiency: {collection_eff:.2f}%")
            print(f"Processing Efficiency: {processing_eff:.2f}%")
            print(f"Overflow Cost: {total_overflow_cost:.2f}")

            # Sanity check
            if collection_eff > 100:
                print("⚠️  WARNING: Collection efficiency > 100% indicates data issue!")
                print("   This suggests double-counting or unit mismatch in tracking.")

            # Store metrics
            metrics_data.append({
                'Scenario': f"{result['inventory_policy']} | {result['stock_strategy']}",
                'Total Generated': total_generated,
                'Total Collected': total_collected,
                'Total Processed': total_processed,
                'Collection Efficiency': min(collection_eff, 100),  # Cap at 100% for display
                'Processing Efficiency': processing_eff,
                'Overflow Cost': total_overflow_cost
            })

        # Create the dashboard visualization
        df = pd.DataFrame(metrics_data)

        fig = sp.make_subplots(
            rows=2, cols=3,
            subplot_titles=['Total Generated (m³)', 'Total Collected (m³)', 'Total Processed (m³)',
                            'Collection Efficiency (%)', 'Processing Efficiency (%)', 'Overflow Cost'],
            vertical_spacing=0.15,
            horizontal_spacing=0.1
        )

        metrics = [
            ('Total Generated', 1, 1),
            ('Total Collected', 1, 2),
            ('Total Processed', 1, 3),
            ('Collection Efficiency', 2, 1),
            ('Processing Efficiency', 2, 2),
            ('Overflow Cost', 2, 3)
        ]

        colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b']

        for i, (metric, row, col) in enumerate(metrics):
            fig.add_trace(
                go.Bar(
                    x=df['Scenario'],
                    y=df[metric],
                    name=metric,
                    showlegend=False,
                    marker_color=colors[i % len(colors)],
                    text=[f'{val:.1f}' for val in df[metric]],
                    textposition='auto'
                ),
                row=row, col=col
            )

        fig.update_layout(
            title="Scenario Comparison Dashboard - Key Performance Metrics",
            height=800,
            showlegend=False
        )

        # Rotate x-axis labels for better readability
        for i in range(1, 7):
            fig.update_xaxes(tickangle=45, row=(i-1)//3 + 1, col=(i-1)%3 + 1)

        # Save the plots
        fig.write_html(f"{self.output_dir}/summary_dashboard.html")
        
        # Create and save metrics summary table
        df.to_html(f"{self.output_dir}/metrics_summary.html", index=False, 
                table_id="metrics-table", classes="table table-striped table-hover")

        return df