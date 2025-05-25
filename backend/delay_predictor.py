import pickle
import datetime
import numpy as np

MODEL_PATH = "backend/model/delay_model.pkl"

try:
    with open(MODEL_PATH, "rb") as f:
        model = pickle.load(f)
except:
    model = None

def extract_features(input_data: dict):
    weather_map = {"clear": 0, "clouds": 1, "rain": 2, "storm": 3, "fog": 4, "snow": 5}
    try:
        hour = datetime.datetime.strptime(input_data["timestamp"], "%Y-%m-%d %H:%M").hour
    except:
        hour = 12
    return np.array([
        input_data.get("distance_km", 5.0),
        input_data.get("traffic_level", 5),
        weather_map.get(input_data.get("weather", "clear").lower(), 0),
        hour
    ]).reshape(1, -1)

def predict_delay(input_data: dict) -> float:
    if model is None:
        return 5.0
    features = extract_features(input_data)
    return round(model.predict(features)[0], 2)
