import pickle
import datetime
import numpy as np
import os

MODEL_PATH = os.path.join(os.path.dirname(__file__), "model/delay_model.pkl")

try:
    with open(MODEL_PATH, "rb") as f:
        model = pickle.load(f)
except Exception as e:
    print("Warning: Model failed to load:", e)
    model = None

def get_weather_severity(weather_label: str) -> int:
    label = weather_label.lower()
    if 'storm' in label or 'tornado' in label: return 9
    if 'snow' in label: return 7
    if 'fog' in label or 'mist' in label or 'haze' in label or 'dust' in label or 'smoke' in label: return 5
    if 'rain' in label or 'drizzle' in label: return 4
    if 'cloud' in label: return 2
    return 1 # clear

def extract_segment_features(segment: dict):
    try:
        dt = segment["timestamp_obj"]
        hour = dt.hour
        day_of_week = dt.weekday()
    except:
        hour = 12
        day_of_week = 0 
        
    is_rush_hour = 1 if hour in [7, 8, 9, 16, 17, 18] else 0
    
    distance_km = segment.get("distance_km", 5.0)
    traffic_level = segment.get("traffic_level", 5)
    weather_encoded = segment.get("weather_severity", 1)
    
    traffic_weather_interaction = traffic_level * weather_encoded
    rush_hour_traffic = traffic_level * is_rush_hour
    distance_weather_risk = distance_km * weather_encoded
    
    # ['distance_km', 'traffic_level', 'weather_encoded', 'hour_of_day', 'day_of_week', 'is_rush_hour',
    #  'traffic_weather_interaction', 'rush_hour_traffic', 'distance_weather_risk']
    return np.array([
        distance_km,
        traffic_level,
        weather_encoded,
        hour,
        day_of_week,
        is_rush_hour,
        traffic_weather_interaction,
        rush_hour_traffic,
        distance_weather_risk
    ]).reshape(1, -1)

def predict_route_segments(segments: list):
    """
    Takes exactly 3 segments from the route.
    Each segment contains: distance_km, traffic_level, weather, timestamp_obj.
    Returns: total_predicted_delay, confidence_score, final_weather_score
    """
    if not segments:
        return 0, "MEDIUM", 1
        
    total_delay = 0.0
    severities = []
    
    for seg in segments:
        sev = get_weather_severity(seg.get("weather", "clear"))
        seg["weather_severity"] = sev
        severities.append(sev)
        
        if model is not None:
            features = extract_segment_features(seg)
            total_delay += model.predict(features)[0]
    
    # 4. WEATHER DECISION LOGIC (NO CONFUSION)
    max_sev = max(severities)
    if max_sev >= 7:
        final_weather_score = max_sev
    else:
        # weighted average based on segment distance (they are equal thirds, so standard average)
        # However, to explicitly respect the request mathematically:
        total_dist = sum(s.get("distance_km", 1) for s in segments)
        if total_dist > 0:
            final_weather_score = sum(s.get("weather_severity", 1) * s.get("distance_km", 1) for s in segments) / total_dist
        else:
            final_weather_score = sum(severities) / len(severities)

    # 7. UNCERTAINTY HANDLING
    volatility = max_sev - min(severities)
    if volatility <= 2:
        confidence = "HIGH (80-90%)"
    elif volatility <= 4:
        confidence = "MEDIUM (60-80%)"
    else:
        confidence = "LOW (40-60%)"
        
    return round(total_delay, 2), confidence, round(final_weather_score, 1)
