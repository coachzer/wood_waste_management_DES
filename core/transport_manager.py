from dataclasses import dataclass
from typing import List, Dict, Optional
from config.constants import TRAVEL_SPEED_KMH
from models.enums import EntityStatus, RegionType, WasteType
from models.distances import get_distance
from utils.capacity_utils import store_with_overflow

@dataclass
class TransportRequest:
    origin: RegionType
    destination: RegionType
    waste_type: WasteType
    volume: float
    request_time: float
    requester_id: str

class PointToPointTransport:
    def __init__(self, state, road_circuity_mean: float, env):
        self.state = state
        state.transport_manager = self
        self.road_circuity_mean = road_circuity_mean
        self.env = env
        self.pending_requests: List[TransportRequest] = []
        self.active_transports: List[Dict] = []
        self._dispatch_scheduled = False

    def _mean_transport_circuity(self) -> float:
        """Deterministic road-circuity factor on the great-circle distance.

        The scenario's transportation_time mean, clamped to at least 1.0
        (ADR 0015). Deterministic by design: this manager is shared across
        collectors and carries no seeded RNG, so the per-trip stochastic draw
        lives on the collection trips, not here.
        """
        return max(1.0, self.road_circuity_mean)

    def travel_time_days(self, from_region: RegionType, to_region: RegionType) -> float:
        """Road travel time between two regions, in days."""
        return get_distance(from_region, to_region) * self._mean_transport_circuity() / TRAVEL_SPEED_KMH / 24.0

    def held_volume_by_requester(self) -> Dict[str, float]:
        held = {}
        for request in self.pending_requests:
            held[request.requester_id] = held.get(request.requester_id, 0.0) + request.volume
        return held

    def in_flight_volume_by_destination(self) -> Dict[str, float]:
        """Volume on vehicles per destination collector name, summed collector by collector."""
        in_flight = {}
        for collector in self.state.collectors:
            for transport in self.active_transports:
                if transport["collector"] is collector:
                    target_name = transport["target_name"]
                    in_flight[target_name] = in_flight.get(target_name, 0.0) + transport["volume"]
        return in_flight

    def request_transport(self, request: TransportRequest) -> bool:
        """Hold the requested volume (at most the center's stock) and queue it. False if none is left."""
        stock = self._origin_collector(request).collection_center.current_storage
        request.volume = min(request.volume, stock[request.waste_type])
        if request.volume <= 0:
            return False
        stock[request.waste_type] -= request.volume
        self.pending_requests.append(request)
        self.schedule_dispatch()
        return True

    def schedule_dispatch(self) -> None:
        if self._dispatch_scheduled:
            return
        self._dispatch_scheduled = True
        self.env.process(self._deferred_dispatch())

    def _deferred_dispatch(self):
        yield self.env.timeout(0)
        self._dispatch_scheduled = False
        for transport in self.process_requests(self.env.now):
            self.active_transports.append(transport)
            self.env.process(self._run_transfer(transport))

    def _run_transfer(self, transport: Dict):
        yield self.env.timeout(max(0.0, transport["arrival_time"] - self.env.now))
        self.deliver(transport)
        self.active_transports.remove(transport)
        vehicle = transport["vehicle"]
        home_region = transport["collector"].region_type
        vehicle.current_load_by_type = {}
        vehicle.current_region = transport["destination"]
        yield self.env.timeout(self.travel_time_days(transport["destination"], home_region))
        vehicle.in_transit = False
        vehicle.current_region = home_region
        self.schedule_dispatch()

    def deliver(self, transport: Dict) -> None:
        destination_collector = self._destination_collector(transport["destination"])
        if destination_collector:
            storage = destination_collector.collection_center.current_storage
            fits = store_with_overflow(destination_collector, storage, transport["load_by_type"])
            for waste_type, volume in fits.items():
                storage[waste_type] += volume
        transport["collector"].charge_trip(
            dict(transport["load_by_type"]), get_distance(transport["origin"], transport["destination"]))

    def find_available_vehicle(self, origin: RegionType) -> Optional[Dict]:
        """Find an idle vehicle at or near the origin. A FAILED collector's vehicles take no new jobs."""
        operating_collectors = [c for c in self.state.collectors if c.status != EntityStatus.FAILED]
        for collector in operating_collectors:
            for vehicle in collector.vehicles:
                if not vehicle.in_transit and vehicle.current_region == origin:
                    return {"vehicle": vehicle, "collector": collector}

        min_distance = float('inf')
        best_option = None

        for collector in operating_collectors:
            for vehicle in collector.vehicles:
                if not vehicle.in_transit:
                    distance = get_distance(vehicle.current_region, origin)
                    if distance < min_distance:
                        min_distance = distance
                        best_option = {"vehicle": vehicle, "collector": collector}

        return best_option

    def process_requests(self, current_time: float) -> List[Dict]:
        if not self.pending_requests:
            return []

        self.pending_requests.sort(key=lambda request: request.request_time)
        requests_by_route = {}
        for request in self.pending_requests:
            requests_by_route.setdefault((request.requester_id, request.destination), []).append(request)

        scheduled_transports = []
        for requests in requests_by_route.values():
            vehicle_info = self.find_available_vehicle(requests[0].origin)
            if not vehicle_info:
                continue
            load_by_type = {}
            for request in requests:
                load_by_type[request.waste_type] = load_by_type.get(request.waste_type, 0.0) + request.volume
            scheduled_transports.append(self._create_transport(requests[0], load_by_type, vehicle_info, current_time))
            for request in requests:
                self.pending_requests.remove(request)

        return scheduled_transports

    def _origin_collector(self, request: TransportRequest):
        return next(c for c in self.state.collectors if c.name == request.requester_id)

    def _destination_collector(self, destination: RegionType):
        return next((c for c in self.state.collectors if c.region_type == destination), None)

    def _create_transport(self, request: TransportRequest, load_by_type: Dict[WasteType, float],
                          vehicle_info: Dict, current_time: float) -> Dict:
        vehicle = vehicle_info["vehicle"]
        collector = vehicle_info["collector"]

        pickup_time = current_time
        if vehicle.current_region != request.origin:
            pickup_time += self.travel_time_days(vehicle.current_region, request.origin)
        arrival_time = pickup_time + self.travel_time_days(request.origin, request.destination)
        volume = sum(load_by_type.values())

        vehicle.in_transit = True
        vehicle.current_load_by_type = dict(load_by_type)

        destination_collector = self._destination_collector(request.destination)
        origin_collector_name = request.requester_id
        target_name = destination_collector.name if destination_collector else origin_collector_name
        for waste_type, waste_volume in load_by_type.items():
            self.state.track_transport_flow(
                source_type="collector",
                source_name=origin_collector_name,
                target_type="collector",
                target_name=target_name,
                waste_type=waste_type,
                volume=waste_volume,
                timestamp=current_time,
                transport_method="inter_region_transport"
            )

        return {
            "vehicle": vehicle,
            "collector": collector,
            "load_by_type": dict(load_by_type),
            "volume": volume,
            "origin": request.origin,
            "destination": request.destination,
            "pickup_time": pickup_time,
            "arrival_time": arrival_time,
            "requester_id": request.requester_id,
            "target_name": target_name,
        }
