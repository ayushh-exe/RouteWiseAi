from fastapi import APIRouter
from pydantic import BaseModel
from typing import List
from backend.delay_predictor import predict_delay  # your delay prediction function
from backend.optimizer import optimize_route
from backend.tomtom_api import get_route_info
from backend.weather_api import get_current_weather
from backend.utils import km_from_travel_time, normalize_traffic_delay

router = APIRouter()

class Stop(BaseModel):
    address: str

class RouteRequest(BaseModel):
    stops: List[Stop]

class DelayRequest(BaseModel):
    origin: str
    destination: str
    timestamp: str

@router.post("/predict-delay")
def predict_delay_endpoint(request: DelayRequest):
    # Fetch travel and traffic delay times (in seconds)
    travel_time_sec, traffic_delay_sec = get_route_info(request.origin, request.destination)
    if travel_time_sec is None or traffic_delay_sec is None:
        return {"error": "Unable to fetch route data."}

    # Calculate distance (km) from travel time
    distance_km = km_from_travel_time(travel_time_sec)

    # Get current weather at origin
    weather = get_current_weather(request.origin) or "clear"

    # Prepare input data for ML model or heuristic
    input_data = {
        "distance_km": distance_km,
        "traffic_level": normalize_traffic_delay(traffic_delay_sec),  # optional, could be removed
        "weather": weather,
        "timestamp": request.timestamp
    }

    # Predict delay in minutes
    delay = predict_delay(input_data)

    base_travel_minutes = travel_time_sec / 60
    total_estimated_time = base_travel_minutes + delay

    # Heuristic for traffic level based on predicted delay
    if delay > 45:
        traffic_level = 9
    elif delay > 30:
        traffic_level = 7
    elif delay > 15:
        traffic_level = 4
    elif delay > 5:
        traffic_level = 2
    else:
        traffic_level = 0

    return {
        "origin": request.origin,
        "destination": request.destination,
        "predicted_delay_minutes": delay,
        "traffic_level": traffic_level,
        "weather": weather,
        "base_travel_minutes": base_travel_minutes,
        "total_estimated_time": total_estimated_time
    }

@router.post("/optimize-route")
def optimize_route_endpoint(request: RouteRequest):
    place_names = [stop.address for stop in request.stops]
    optimized_order = optimize_route(place_names)
    return {
        "original_order": place_names,
        "optimized_order": optimized_order
    }
