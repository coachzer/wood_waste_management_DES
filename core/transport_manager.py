from dataclasses import dataclass
from typing import List, Dict, Optional
from config.constants import TRAVEL_SPEED_KMH
from models.enums import EntityStatus, RegionType, WasteType
from models.distances import get_distance

@dataclass
class TransportRequest:
    origin: RegionType
    destination: RegionType
    waste_type: WasteType
    volume: float
    request_time: float
    requester_id: str

class PointToPointTransport:
    def __init__(self, state, road_circuity_mean: float):
        self.state = state
        self.road_circuity_mean = road_circuity_mean
        self.pending_requests: List[TransportRequest] = []

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

    def queued_volume(self, requester_id: str, waste_type: WasteType) -> float:
        """Volume of this waste type that queued requests from this collector have claimed."""
        return sum(request.volume for request in self.pending_requests
                   if request.requester_id == requester_id and request.waste_type == waste_type)

    def request_transport(self, request: TransportRequest):
        self.pending_requests.append(request)
    
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
        """Process pending transport requests and create transport jobs"""
        if not self.pending_requests:
            return []
        
        self.pending_requests.sort(key=lambda r: r.request_time)
        
        scheduled_transports = []
        processed_requests = []
        
        for request in self.pending_requests:
            loadable_volume = self._loadable_volume(request)
            if loadable_volume <= 0:
                processed_requests.append(request)
                continue
            vehicle_info = self.find_available_vehicle(request.origin)
            if vehicle_info:
                request.volume = loadable_volume
                self._origin_collector(request).collection_center.current_storage[request.waste_type] -= loadable_volume
                scheduled_transports.append(self._create_transport(request, vehicle_info, current_time))
                processed_requests.append(request)
        
        for request in processed_requests:
            self.pending_requests.remove(request)
        
        return scheduled_transports
    
    def _origin_collector(self, request: TransportRequest):
        return next(c for c in self.state.collectors if c.name == request.requester_id)

    def _loadable_volume(self, request: TransportRequest) -> float:
        """Volume still at the sending center. Queued volume stays there until a vehicle loads it."""
        stock = self._origin_collector(request).collection_center.current_storage[request.waste_type]
        return min(request.volume, stock)

    def _create_transport(self, request: TransportRequest, vehicle_info: Dict, current_time: float) -> Dict:
        """Create a transport job from a request"""
        vehicle = vehicle_info["vehicle"]
        collector = vehicle_info["collector"]
        
        travel_time = self.travel_time_days(request.origin, request.destination)

        pickup_time = current_time
        if vehicle.current_region != request.origin:
            pickup_time += self.travel_time_days(vehicle.current_region, request.origin)
        
        arrival_time = pickup_time + travel_time
        
        vehicle.in_transit = True
        vehicle.current_load_by_type = {request.waste_type: request.volume}

        state = self.state
        destination_collector = next(
            (c for c in state.collectors
             if c.region_type == request.destination),
            None
        )
        origin_collector_name = request.requester_id
        target_name = destination_collector.name if destination_collector else origin_collector_name

        self.state.track_transport_flow(
            source_type="collector",
            source_name=origin_collector_name,
            target_type="collector",
            target_name=target_name,
            waste_type=request.waste_type,
            volume=request.volume,
            timestamp=current_time,
            transport_method="inter_region_transport"
        )
        
        transport = {
            "vehicle": vehicle,
            "collector": collector,
            "waste_type": request.waste_type,
            "volume": request.volume,
            "origin": request.origin,
            "destination": request.destination,
            "pickup_time": pickup_time,
            "arrival_time": arrival_time,
            "requester_id": request.requester_id,
            "target_name": target_name,
        }
        return transport