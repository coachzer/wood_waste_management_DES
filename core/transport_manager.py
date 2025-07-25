from dataclasses import dataclass
from typing import List, Dict, Optional
from enum import Enum
from models.enums import RegionType, WasteType
from models.distances import get_distance
from models.state import SimulationState

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
    def __init__(self):
        self.pending_requests: List[TransportRequest] = []
        self.active_transports: List[Dict] = []
        
    def request_transport(self, request: TransportRequest) -> bool:
        print(f"[TRANSPORT DEBUG] Request received: {request.volume:.2f} m³ {request.waste_type.value}")
        self.pending_requests.append(request)
        print(f"[TRANSPORT DEBUG] Total pending requests: {len(self.pending_requests)}")
        return True
    
    def find_available_vehicle(self, origin: RegionType) -> Optional[Dict]:
        """Find an available vehicle at or near the origin"""
        state = SimulationState.get_instance()
        print(f"[VEHICLE DEBUG] Looking for vehicles at {origin.value}")
    
        vehicle_count = 0
        available_count = 0
        
        for collector in state.collectors:
            for vehicle in collector.vehicles:
                vehicle_count += 1
                if not vehicle.in_transit:
                    available_count += 1
                    print(f"[VEHICLE DEBUG] Available: {vehicle.id} at {vehicle.current_region.value}")
        
        print(f"[VEHICLE DEBUG] Total vehicles: {vehicle_count}, Available: {available_count}")

        
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
        
        # Calculate travel time (assuming 50 km/h average speed)
        distance = get_distance(request.origin, request.destination)
        travel_time = distance / 50.0 / 24.0
        
        # Check if vehicle needs to travel to origin first
        pickup_time = current_time
        if vehicle.current_region != request.origin:
            pickup_distance = get_distance(vehicle.current_region, request.origin)
            pickup_time += pickup_distance / 50.0
        
        arrival_time = pickup_time + travel_time
        
        # Update vehicle status
        vehicle.in_transit = True
        vehicle.destination = request.destination
        vehicle.estimated_arrival = arrival_time
        vehicle.current_load = request.volume
        
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
        
        print(f"{current_time}: Scheduled transport of {request.volume:.2f} m³ {request.waste_type.value} "
              f"from {request.origin.value} to {request.destination.value}, ETA: {arrival_time:.2f}")
        
        return transport