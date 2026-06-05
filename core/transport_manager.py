from dataclasses import dataclass
from typing import List, Dict, Optional
from enum import Enum
from config.constants import TRAVEL_SPEED_KMH
from models.enums import RegionType, WasteType
from models.distances import get_distance

class TransportPriority(Enum):
    LOW = 1
    NORMAL = 2
    HIGH = 3
    URGENT = 4

@dataclass
class TransportRequest:
    origin: RegionType
    destination: RegionType
    waste_type: WasteType
    volume: float
    priority: TransportPriority
    request_time: float
    requester_id: str  

class PointToPointTransport:
    def __init__(self, state=None):
        self.state = state
        self.pending_requests: List[TransportRequest] = []
        self.active_transports: List[Dict] = []
        
    def request_transport(self, request: TransportRequest) -> bool:
        self.pending_requests.append(request)
        return True
    
    def find_available_vehicle(self, origin: RegionType) -> Optional[Dict]:
        """Find an available vehicle at or near the origin"""
        state = self.state
        # Look for vehicles in the origin region first
        for collector in state.collectors:
            for vehicle in collector.vehicles:
                if not vehicle.in_transit and vehicle.current_region == origin:
                    return {"vehicle": vehicle, "collector": collector}
        
        # If none found, look for nearest available vehicle
        min_distance = float('inf')
        best_option = None
        
        for collector in state.collectors:
            for vehicle in collector.vehicles:
                if not vehicle.in_transit:
                    distance = get_distance(vehicle.current_region, origin)
                    if distance < min_distance:
                        min_distance = distance
                        best_option = {"vehicle": vehicle, "collector": collector, "distance": distance}
        
        return best_option
    
    def process_requests(self, current_time: float) -> List[Dict]:
        """Process pending transport requests and create transport jobs"""
        if not self.pending_requests:
            return []
        
        # Sort by priority and time
        self.pending_requests.sort(key=lambda r: (r.priority.value, r.request_time), reverse=True)
        
        scheduled_transports = []
        processed_requests = []
        
        for request in self.pending_requests:
            vehicle_info = self.find_available_vehicle(request.origin)
            if vehicle_info:
                transport = self._create_transport(request, vehicle_info, current_time)
                if transport:
                    scheduled_transports.append(transport)
                    processed_requests.append(request)
        
        # Remove processed requests
        for request in processed_requests:
            self.pending_requests.remove(request)
        
        return scheduled_transports
    
    def _create_transport(self, request: TransportRequest, vehicle_info: Dict, current_time: float) -> Optional[Dict]:
        """Create a transport job from a request"""
        vehicle = vehicle_info["vehicle"]
        collector = vehicle_info["collector"]
        
        distance = get_distance(request.origin, request.destination)
        travel_time = distance / TRAVEL_SPEED_KMH / 24.0

        pickup_time = current_time
        if vehicle.current_region != request.origin:
            pickup_distance = get_distance(vehicle.current_region, request.origin)
            pickup_time += pickup_distance / TRAVEL_SPEED_KMH / 24.0
        
        arrival_time = pickup_time + travel_time
        
        # Update vehicle status
        vehicle.in_transit = True
        vehicle.destination = request.destination
        vehicle.estimated_arrival = arrival_time
        vehicle.current_load = request.volume
        vehicle.current_load_by_type = {request.waste_type: request.volume}

        state = self.state
        # Cross-region repositioning is physical movement between two collectors'
        # collection centers (ADR 0009), logged collector -> collector so no
        # bullwhip echelon reads it as treatment intake.
        destination_collector = next(
            (c for c in state.collectors
             if c.region_type == request.destination),
            None
        )
        target_name = destination_collector.name if destination_collector else request.requester_id

        # The source is the ORIGIN collector that decremented its own storage
        # (named by requester_id), NOT the carrier -- find_available_vehicle may
        # borrow a vehicle from another region, and sourcing on it would
        # mis-attribute the outflow and break the per-collection-center identity.
        self.state.track_transport_flow(
            source_type="collector",
            source_name=request.requester_id,
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
            "priority": request.priority,
            "requester_id": request.requester_id
        }
        return transport