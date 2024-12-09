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
        if env.now == 100:
            print(f"\n=== System State at Time {env.now} ===")
            waste_monitor.generate_summary_report()

            # Generate plots
            waste_monitor.plot_generation_trends(f"plots/generation_t{env.now}.png")
            waste_monitor.plot_collection_efficiency(f"plots/collection_t{env.now}.png")
            waste_monitor.plot_storage_levels(f"plots/storage_t{env.now}.png")

            waste_monitor.plot_detailed_storage_analysis(
                f"plots/storage_detailed_t{env.now}.png"
            )
            waste_monitor.plot_temporal_analysis()
            waste_monitor.plot_generator_metrics()
            waste_monitor.plot_collector_metrics()
            waste_monitor.plot_treatment_metrics()
            waste_monitor.plot_system_performance()

            # TO-DO
            # waste_monitor.plot_created_products()

        yield env.timeout(1)
