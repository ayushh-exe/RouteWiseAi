import requests
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
import pickle
import os
import time

# API keys
TOMTOM_API_KEY = "y3lqXrAZjVCThGRsEFVLiiJb5GSUpmI1"
WEATHER_API_KEY = "81b66e6697efb2b8adaa3f99f877b664"

cities = [
    ("Delhi", 28.6139, 77.2090),
    ("Mumbai", 19.0760, 72.8777),
    ("Bangalore", 12.9716, 77.5946),
    ("Chennai", 13.0827, 80.2707),
    ("Kolkata", 22.5726, 88.3639),
    ("Hyderabad", 17.3850, 78.4867),
    ("Pune", 18.5204, 73.8567),
    ("Ahmedabad", 23.0225, 72.5714),
    ("Jaipur", 26.9124, 75.7873),
    ("Lucknow", 26.8467, 80.9462),
]

weather_map = {
    "Clear": 0,
    "Clouds": 1,
    "Rain": 2,
    "Thunderstorm": 3,
    "Drizzle": 4,
    "Mist": 5,
    "Fog": 6,
    "Haze": 7,
    "Dust": 8,
    "Smoke": 9,
    "Snow": 10,
    "Squall": 11,
    "Tornado": 12
}

def get_weather(lat, lon):
    url = f"https://api.openweathermap.org/data/2.5/weather"
    params = {
        "lat": lat,
        "lon": lon,
        "appid": WEATHER_API_KEY
    }
    try:
        res = requests.get(url, params=params)
        res.raise_for_status()
        weather_main = res.json()["weather"][0]["main"]
        return weather_main, weather_map.get(weather_main, -1)
    except Exception as e:
        print(f"❌ Weather API error: {e}")
        return "Unknown", -1

def fetch_data():
    data = []
    for i in range(len(cities)):
        for j in range(len(cities)):
            if i != j:
                from_name, lat1, lon1 = cities[i]
                to_name, lat2, lon2 = cities[j]

                # TomTom Route
                url = f"https://api.tomtom.com/routing/1/calculateRoute/{lat1},{lon1}:{lat2},{lon2}/json"
                params = {
                    "traffic": "true",
                    "travelMode": "car",
                    "key": TOMTOM_API_KEY
                }

                try:
                    res = requests.get(url, params=params)
                    res.raise_for_status()
                    route = res.json()["routes"][0]["summary"]

                    # Real Weather from origin city
                    weather_label, weather_encoded = get_weather(lat1, lon1)

                    data.append({
                        "from_city": from_name,
                        "to_city": to_name,
                        "distance_km": round(route["lengthInMeters"] / 1000, 2),
                        "traffic_delay_min": round(route.get("trafficDelayInSeconds", 0) / 60, 2),
                        "travel_time_min": round(route["travelTimeInSeconds"] / 60, 2),
                        "weather": weather_label,
                        "weather_encoded": weather_encoded
                    })

                    print(f"✅ {from_name} → {to_name} | Weather: {weather_label}")
                    time.sleep(1.5)

                except Exception as e:
                    print(f"❌ Failed route {from_name} → {to_name}: {e}")

    return pd.DataFrame(data)

# Start
print("📡 Collecting real data from TomTom and OpenWeatherMap...")
df = fetch_data()

# Save dataset
os.makedirs("model", exist_ok=True)
df.to_csv("model/dataset.csv", index=False)
print("📁 Saved real dataset to model/dataset.csv")

# Train model
X = df[["distance_km", "traffic_delay_min", "weather_encoded"]]
y = df["travel_time_min"]

model = RandomForestRegressor(n_estimators=100, random_state=42)
model.fit(X, y)

# Save model
with open("model/delay_model.pkl", "wb") as f:
    pickle.dump(model, f)

print("✅ Trained model saved to model/delay_model.pkl")
