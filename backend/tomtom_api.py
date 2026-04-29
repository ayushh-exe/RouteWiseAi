import requests
import pandas as pd
import os

TOMTOM_API_KEY = "y3lqXrAZjVCThGRsEFVLiiJb5GSUpmI1"


def load_city_coordinates_from_dataset():
    """Loads city coordinates from the training dataset to reduce API calls."""
    coords = {}

    dataset_path = os.path.join(os.path.dirname(__file__), '..', 'model', 'dataset.csv')
    try:
        if os.path.exists(dataset_path):
            df = pd.read_csv(dataset_path)

            for _, row in df.iterrows():

                city_name = row['from_city'].title()

    except Exception as e:
        print(f"Could not load or process dataset for coordinates: {e}")
    return coords


CITY_COORDS_CACHE = load_city_coordinates_from_dataset()



def geocode_place(place_name: str):
    """
    Geocodes a place name to latitude and longitude.
    First checks the local cache, then falls back to TomTom API.
    """

    formatted_name = place_name.strip().title()
    if formatted_name in CITY_COORDS_CACHE:

        return CITY_COORDS_CACHE[formatted_name]


# If not in cache, call the API

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

def get_route_info(origin, destination):
    if isinstance(origin, str): origin_coords = geocode_place(origin)
    else: origin_coords = origin

    if isinstance(destination, str): dest_coords = geocode_place(destination)
    else: dest_coords = destination

    if not origin_coords or not dest_coords: return None, None

    url = f"https://api.tomtom.com/routing/1/calculateRoute/{origin_coords[0]},{origin_coords[1]}:{dest_coords[0]},{dest_coords[1]}/json"
    params = { "key": TOMTOM_API_KEY, "traffic": "true", "travelMode": "car", "computeTravelTimeFor": "all", "routeType": "fastest" }
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        summary = data["routes"][0]["summary"]
        return summary["travelTimeInSeconds"], summary.get("trafficDelayInSeconds", 0)
    except:
        return None, None

def get_route_path(origin_coords, dest_coords):
    if not origin_coords or not dest_coords: return []
    
    url = f"https://api.tomtom.com/routing/1/calculateRoute/{origin_coords[0]},{origin_coords[1]}:{dest_coords[0]},{dest_coords[1]}/json"
    params = { "key": TOMTOM_API_KEY, "traffic": "true" }
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        points = data["routes"][0]["legs"][0]["points"]
        return [[p['latitude'], p['longitude']] for p in points]
    except Exception as e:
        print(f"Error fetching route path: {e}")
        return []