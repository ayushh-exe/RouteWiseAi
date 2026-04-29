import requests
from backend.tomtom_api import geocode_place
import datetime

WEATHER_API_KEY = "81b66e6697efb2b8adaa3f99f877b664"

def get_weather(place_name: str) -> str:
    lat, lon = geocode_place(place_name)
    if lat is None or lon is None:
        return "clear"
    url = "https://api.openweathermap.org/data/2.5/weather"
    params = {"lat": lat, "lon": lon, "appid": WEATHER_API_KEY, "units": "metric"}
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        return data["weather"][0]["main"].lower()
    except:
        return "clear"

def get_forecast_by_coords(lat: float, lon: float, target_timestamp: datetime.datetime) -> str:
    """Fetches the weather forecast for exactly when the driver is expected to arrive at this coordinate."""
    url = "https://api.openweathermap.org/data/2.5/forecast"
    params = {"lat": lat, "lon": lon, "appid": WEATHER_API_KEY, "units": "metric"}
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        
        target_timestamp_epoch = target_timestamp.timestamp()
        
        best_forecast = "clear"
        min_diff = float("inf")
        
        for forecast_chunk in data.get("list", []):
            chunk_time = forecast_chunk["dt"]
            diff = abs(chunk_time - target_timestamp_epoch)
            if diff < min_diff:
                min_diff = diff
                best_forecast = forecast_chunk["weather"][0]["main"].lower()
                
        return best_forecast
    except Exception as e:
        print(f"Error fetching forecast for lat:{lat} lon:{lon} -> {e}")
        return "clear"

def get_detailed_forecast_by_coords(lat: float, lon: float, target_timestamp: datetime.datetime) -> dict:
    """Fetches detailed weather forecast (temp, humidity, wind, icon) for a specific coordinate and time."""
    url = "https://api.openweathermap.org/data/2.5/forecast"
    params = {"lat": lat, "lon": lon, "appid": WEATHER_API_KEY, "units": "metric"}
    default = {
        "condition": "clear", "temperature": None, "feels_like": None,
        "humidity": None, "wind_speed": None, "icon": "01d", "description": "clear sky"
    }
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()

        target_epoch = target_timestamp.timestamp()
        best = None
        min_diff = float("inf")

        for chunk in data.get("list", []):
            diff = abs(chunk["dt"] - target_epoch)
            if diff < min_diff:
                min_diff = diff
                best = chunk

        if best:
            return {
                "condition": best["weather"][0]["main"].lower(),
                "description": best["weather"][0].get("description", ""),
                "temperature": round(best["main"]["temp"], 1),
                "feels_like": round(best["main"].get("feels_like", best["main"]["temp"]), 1),
                "humidity": best["main"].get("humidity"),
                "wind_speed": round(best.get("wind", {}).get("speed", 0), 1),
                "icon": best["weather"][0].get("icon", "01d"),
            }
        return default
    except Exception as e:
        print(f"Error fetching detailed forecast for lat:{lat} lon:{lon} -> {e}")
        return default


import aiohttp

async def async_get_combined_forecast(session: aiohttp.ClientSession, lat: float, lon: float, target_timestamp: datetime.datetime) -> dict:
    """
    Async version: fetches weather forecast for a coordinate and returns BOTH
    the simple weather label and the detailed dict from a SINGLE API call.
    """
    url = "https://api.openweathermap.org/data/2.5/forecast"
    params = {"lat": lat, "lon": lon, "appid": WEATHER_API_KEY, "units": "metric"}
    default_detailed = {
        "condition": "clear", "temperature": None, "feels_like": None,
        "humidity": None, "wind_speed": None, "icon": "01d", "description": "clear sky"
    }
    try:
        async with session.get(url, params=params) as response:
            response.raise_for_status()
            data = await response.json()

        target_epoch = target_timestamp.timestamp()
        best = None
        min_diff = float("inf")

        for chunk in data.get("list", []):
            diff = abs(chunk["dt"] - target_epoch)
            if diff < min_diff:
                min_diff = diff
                best = chunk

        if best:
            weather_label = best["weather"][0]["main"].lower()
            detailed = {
                "condition": weather_label,
                "description": best["weather"][0].get("description", ""),
                "temperature": round(best["main"]["temp"], 1),
                "feels_like": round(best["main"].get("feels_like", best["main"]["temp"]), 1),
                "humidity": best["main"].get("humidity"),
                "wind_speed": round(best.get("wind", {}).get("speed", 0), 1),
                "icon": best["weather"][0].get("icon", "01d"),
            }
            return {"weather_label": weather_label, "detailed": detailed}

        return {"weather_label": "clear", "detailed": default_detailed}
    except Exception as e:
        print(f"Error fetching async forecast for lat:{lat} lon:{lon} -> {e}")
        return {"weather_label": "clear", "detailed": default_detailed}