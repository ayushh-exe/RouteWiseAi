import requests
import aiohttp
import asyncio
import time
import math
import os
from dotenv import load_dotenv

load_dotenv()


TOMTOM_API_KEY = os.getenv("TOMTOM_API_KEY", "YOUR_DEFAULT_API_KEY")

# In-memory cache for routes: (lat1, lon1, lat2, lon2) -> (data, expiry)
# Using a 5-minute TTL (300 seconds)
global_route_cache = {}
CACHE_TTL = 300

def haversine_fallback(lat1, lon1, lat2, lon2):
    """Fallback: Estimate travel time using Haversine distance and average speed (60km/h)."""
    R = 6371  # Radius of the earth in km
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) * math.sin(dlat / 2) + \
        math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * \
        math.sin(dlon / 2) * math.sin(dlon / 2)
    c = 2 * math.asin(math.sqrt(a))
    dist_km = R * c
    
    # Estimate: 60 km/h = 1 km per minute
    time_sec = (dist_km / 60) * 3600
    return time_sec, 0, dist_km, [] # 0 delay, empty path

def geocode_place(place_name: str):
    """Converts a place name to latitude and longitude with retry logic."""
    url = f"https://api.tomtom.com/search/2/search/{place_name}.json"
    params = {"key": TOMTOM_API_KEY, "limit": 1}
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = requests.get(url, params=params)
            
            # Handle rate limiting specifically
            if response.status_code == 429:
                wait_time = (attempt + 1) * 0.5
                print(f"[GEOCODE] Rate limited for {place_name}. Retrying in {wait_time}s...")
                time.sleep(wait_time)
                continue
                
            response.raise_for_status()
            data = response.json()
            if data["results"]:
                pos = data["results"][0]["position"]
                return pos["lat"], pos["lon"]
            return None, None
            
        except requests.RequestException as e:
            if attempt == max_retries - 1:
                print(f"Error geocoding {place_name} after {max_retries} attempts: {e}")
                return None, None
            time.sleep(0.3)
    return None, None

def reverse_geocode(lat: float, lon: float):
    """Converts coordinates to a freeform address string."""
    url = f"https://api.tomtom.com/search/2/reverseGeocode/{lat},{lon}.json"
    params = {"key": TOMTOM_API_KEY}
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        if data.get("addresses"):
            return data["addresses"][0]["address"].get("freeformAddress")
        return None
    except requests.RequestException as e:
        print(f"Error reverse geocoding: {e}")
        return None

def check_route_cache(lat1, lon1, lat2, lon2):
    """Checks the global cache for a pre-existing route."""
    cache_key = (round(lat1, 4), round(lon1, 4), round(lat2, 4), round(lon2, 4))
    if cache_key in global_route_cache:
        data, expiry = global_route_cache[cache_key]
        if time.time() < expiry:
            return data, cache_key
    return None, cache_key

def get_route_info(origin_coords, dest_coords):
    """Gets travel time, live traffic delay, and path for a route between two coordinates."""
    lat1, lon1 = origin_coords
    lat2, lon2 = dest_coords
    
    # Check Cache
    cached_data, cache_key = check_route_cache(lat1, lon1, lat2, lon2)
    if cached_data:
        print(f"[CACHE HIT] {cache_key}")
        return cached_data

    url = f"https://api.tomtom.com/routing/1/calculateRoute/{lat1},{lon1}:{lat2},{lon2}/json"
    params = {
        "key": TOMTOM_API_KEY,
        "travelMode": "car",
        "computeTravelTimeFor": "all",
        "traffic": "true"
    }
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        if "routes" in data and data["routes"]:
            route = data["routes"][0]
            summary = route["summary"]
            
            # Base travel time
            base_travel_time_sec = summary.get("noTrafficTravelTimeInSeconds", summary["travelTimeInSeconds"])
            
            # Real traffic delay
            live_travel_time_sec = summary.get("liveTrafficIncidentsTravelTimeInSeconds", summary["travelTimeInSeconds"])
            traffic_delay_sec = max(0, live_travel_time_sec - base_travel_time_sec)
            
            distance_km = summary.get("lengthInMeters", 0) / 1000
            
            path = [(p["latitude"], p["longitude"]) for p in route["legs"][0]["points"]]
            result = (base_travel_time_sec, traffic_delay_sec, distance_km, path)
            
            # Store in cache
            global_route_cache[cache_key] = (result, time.time() + CACHE_TTL)
            return result
        return None, None, None, None
    except requests.RequestException as e:
        print(f"Error getting route info: {e}")
        return None, None, None, None

async def get_route_info_async(origin_coords, dest_coords, session: aiohttp.ClientSession):
    """Async version: Gets route info from TomTom with caching and fallback."""
    lat1, lon1 = origin_coords
    lat2, lon2 = dest_coords
    
    # 1. Check Cache
    cached_data, cache_key = check_route_cache(lat1, lon1, lat2, lon2)
    if cached_data:
        print(f"[ASYNC CACHE HIT] {cache_key}")
        return cached_data
            
    # 2. API Call
    url = f"https://api.tomtom.com/routing/1/calculateRoute/{lat1},{lon1}:{lat2},{lon2}/json"
    params = {
        "key": TOMTOM_API_KEY,
        "travelMode": "car",
        "computeTravelTimeFor": "all",
        "traffic": "true"
    }
    
    try:
        async with session.get(url, params=params, timeout=5) as response:
            if response.status == 200:
                data = await response.json()
                if "routes" in data and data["routes"]:
                    route = data["routes"][0]
                    summary = route["summary"]
                    base_time = summary.get("noTrafficTravelTimeInSeconds", summary["travelTimeInSeconds"])
                    live_time = summary.get("liveTrafficIncidentsTravelTimeInSeconds", summary["travelTimeInSeconds"])
                    traffic_delay = max(0, live_time - base_time)
                    distance_km = summary.get("lengthInMeters", 0) / 1000
                    path = [(p["latitude"], p["longitude"]) for p in route["legs"][0]["points"]]
                    
                    result = (base_time, traffic_delay, distance_km, path)
                    
                    # Store in cache
                    global_route_cache[cache_key] = (result, time.time() + CACHE_TTL)
                    return result
            
            # If status not 200 or no routes, fallback
            return haversine_fallback(lat1, lon1, lat2, lon2)
            
    except Exception as e:
        print(f"Async API Error: {e}. Using Haversine fallback.")
        return haversine_fallback(lat1, lon1, lat2, lon2)