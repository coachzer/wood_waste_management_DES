from models.config import SIMULATION_DURATION


def monitor_system(env, waste_monitor, generators, collectors, treatment_operators):
    """Process to monitor system state periodically"""
    while True:
        # Track all entities
        for generator in generators:
            waste_monitor.track_generation(generator, env.now)
        for collector in collectors:
            waste_monitor.track_collection(collector, env.now)
        for treatment in treatment_operators:
            waste_monitor.track_processing(treatment, env.now)

        # Generate reports
        if env.now == SIMULATION_DURATION - 1:
            print(f"\n=== System State at Time {env.now} ===")
            waste_monitor.generate_summary_report()

            # Generate all plots using temporal analysis
            waste_monitor.plot_temporal_analysis()

        yield env.timeout(1)
