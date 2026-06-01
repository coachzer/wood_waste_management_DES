LANDFILL_EMISSIONS_PER_M3 = 0.24  # t CO2e per m³
LANDFILL_EMISSIONS_PER_M3_KG = 0.24 * 1_000  # 240 kg CO2e / m³
TRANSPORT_EMISSIONS_PER_TON_KM = 0.087  # kg eCO2 per ton-kilometer or 87 g CO2e/ton km
DENSITY = 0.6
TRANSPORT_EMISSIONS_PER_M3_KM = 0.087 * DENSITY
SIMULATION_DURATION = 365  # days in simulation (one full year)
EXPANSION_SIZE_M3 = 500  # 500m³ expansion size

LOCAL_COLLECTION_RATIO = 0.8
ON_DEMAND_BUFFER_RATIO = 0.15
ON_DEMAND_TARGET_RATIO = 0.35
FAILED_ENTITY_EFFICIENCY = 0.1
RECOVERING_BASE_EFFICIENCY = 0.3
HISTORY_BUFFER_SIZE = 1000
SEASONAL_PERIODS = 4
SEASONAL_AMPLITUDE = 0.2  # +/- fraction of the seasonal sinusoid about a unit mean
TRAVEL_SPEED_KMH = 50.0

# Market consumption (demand-as-continuous-consumption model, ADR 0002)
WEEKS_PER_YEAR = 52  # annual demand is spread across this many consumption ticks
CONSUMPTION_INTERVAL_DAYS = 7  # the market consumes finished goods weekly
MARKET_SIGNAL_PRIORITY = 10  # kanban priority of downstream market-demand signals