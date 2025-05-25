import requests
from backend.tomtom_api import geocode_place

WEATHER_API_KEY = "81b66e6697efb2b8adaa3f99f877b664"

def get_current_weather(place_name: str) -> str:
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
