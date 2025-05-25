import requests

TOMTOM_API_KEY = "y3lqXrAZjVCThGRsEFVLiiJb5GSUpmI1"

def geocode_place(place_name: str):
    url = f"https://api.tomtom.com/search/2/geocode/{place_name}.json"
    params = {"key": TOMTOM_API_KEY}
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        if data["results"]:
            position = data["results"][0]["position"]
            return position["lat"], position["lon"]
    except:
        pass
    return None, None

def get_route_info(origin_name: str, destination_name: str):
    origin = geocode_place(origin_name)
    destination = geocode_place(destination_name)
    if not origin or not destination:
        return None, None
    url = f"https://api.tomtom.com/routing/1/calculateRoute/{origin[0]},{origin[1]}:{destination[0]},{destination[1]}/json"
    params = {
        "key": TOMTOM_API_KEY,
        "traffic": "true",
        "travelMode": "car",
        "computeTravelTimeFor": "all",
        "routeType": "fastest"
    }
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        summary = data["routes"][0]["summary"]
        return summary["travelTimeInSeconds"], summary.get("trafficDelayInSeconds", 0)
    except:
        return None, None