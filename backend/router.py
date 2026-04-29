from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import text

from backend.database import get_db
from backend.delay_predictor import predict_delay
from backend.optimizer import optimize_route
from backend.tomtom_api import get_route_info, geocode_place
from backend.weather_api import get_current_weather
from backend.utils import km_from_travel_time, normalize_traffic_delay

router = APIRouter()

# --- Pydantic Models ---
class Stop(BaseModel): address: str
class RouteRequest(BaseModel): stops: List[Stop]
class DelayRequest(BaseModel): origin: str; destination: str; timestamp: str
class TransportRequest(BaseModel): origin: str; destination: str
class OptimizedStop(BaseModel): name: str; lat: float; lon: float
class OptimizedRouteResponse(BaseModel): optimized_stops: List[OptimizedStop]; route_path: List[List[float]]

class TransportOption(BaseModel):
    id: int
    transport_type: str
    origin_city: str
    destination_city: str
    operator_name: Optional[str] = None
    departure_time: Optional[str] = None
    arrival_time: Optional[str] = None
    duration: Optional[str] = None
    fare: Optional[int] = None
    seats_available: Optional[int] = None
    details: Optional[dict] = None

# New response model for the delay prediction to include map data
class DelayResponse(BaseModel):
    origin: str
    destination: str
    predicted_delay_minutes: float
    traffic_level: int
    weather: str
    base_travel_minutes: float
    total_estimated_time: float
    route_path: List[List[float]]
    stops: List[OptimizedStop]

# --- API Endpoints ---
@router.post("/predict-delay", response_model=DelayResponse)
def predict_delay_endpoint(request: DelayRequest):
    origin_coords = geocode_place(request.origin)
    dest_coords = geocode_place(request.destination)

    if not origin_coords or not dest_coords:
        raise HTTPException(status_code=404, detail="Could not geocode origin or destination.")

    base_travel_time_sec, traffic_delay_sec, distance_km, route_path = get_route_info(origin_coords, dest_coords)
    if base_travel_time_sec is None or traffic_delay_sec is None:
        raise HTTPException(status_code=503, detail="Unable to fetch route data from provider.")
    weather = get_current_weather(request.origin) or "clear"
    input_data = {
        "distance_km": distance_km,
        "traffic_level": normalize_traffic_delay(traffic_delay_sec),
        "weather": weather,
        "timestamp": request.timestamp
    }
    delay = predict_delay(input_data)
    base_travel_minutes = base_travel_time_sec / 60
    total_estimated_time = base_travel_minutes + delay

    if delay > 45: traffic_level = 9
    elif delay > 30: traffic_level = 7
    elif delay > 15: traffic_level = 4
    elif delay > 5: traffic_level = 2
    else: traffic_level = 0

    # Prepare stops data for map markers
    stops_for_map = [
        OptimizedStop(name=request.origin, lat=origin_coords[0], lon=origin_coords[1]),
        OptimizedStop(name=request.destination, lat=dest_coords[0], lon=dest_coords[1])
    ]

    return DelayResponse(
        origin=request.origin,
        destination=request.destination,
        predicted_delay_minutes=delay,
        traffic_level=traffic_level,
        weather=weather,
        base_travel_minutes=base_travel_minutes,
        total_estimated_time=total_estimated_time,
        route_path=route_path,
        stops=stops_for_map
    )

@router.post("/optimize-route", response_model=OptimizedRouteResponse)
def optimize_route_endpoint(request: RouteRequest):
    place_names = [stop.address for stop in request.stops]
    optimized_stops = optimize_route(place_names)
    
    full_route_path = []
    if len(optimized_stops) >= 2:
        for i in range(len(optimized_stops) - 1):
            origin_stop = optimized_stops[i]
            dest_stop = optimized_stops[i+1]
            origin_coords = (origin_stop['lat'], origin_stop['lon'])
            dest_coords = (dest_stop['lat'], dest_stop['lon'])
            _, _, _, segment_path = get_route_info(origin_coords, dest_coords)
            if segment_path:
                full_route_path.extend(segment_path)

    return OptimizedRouteResponse(
        optimized_stops=[OptimizedStop(**s) for s in optimized_stops],
        route_path=full_route_path
    )


@router.post("/find-transport", response_model=List[TransportOption])
def find_transport_endpoint(request: TransportRequest, db: Session = Depends(get_db)):
    query = text("""
        SELECT * FROM transport_options
        WHERE origin_city ILIKE :origin AND destination_city ILIKE :destination
        ORDER BY transport_type, fare ASC;
    """)
    result = db.execute(query, {"origin": f"%{request.origin}%", "destination": f"%{request.destination}%"})
    
    # Manually map RowMapping to dict before creating Pydantic model
    transport_options = [TransportOption.model_validate(row) for row in result.mappings()]
    return transport_options

