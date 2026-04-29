#PYTHONPATH=. uvicorn backend.main:app --reload
from fastapi import FastAPI, HTTPException, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr
from sqlalchemy import create_engine, text
import os
from dotenv import load_dotenv
import bcrypt
import aiohttp
import asyncio


from .optimizer import find_optimal_route
from .delay_predictor import predict_route_segments, get_weather_severity
from .weather_api import get_weather, get_forecast_by_coords, get_detailed_forecast_by_coords, async_get_combined_forecast
from .tomtom_api import get_route_info, geocode_place, reverse_geocode, get_route_info_async
from .utils import km_from_travel_time, normalize_traffic_delay
from typing import Optional

# --- Password Hashing Setup using raw bcrypt ---

# --- Database Connection ---
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable not set.")
engine = create_engine(DATABASE_URL)

app = FastAPI()

# --- Mount Static Files ---
app.mount("/static", StaticFiles(directory="frontend/static"), name="static")


# --- Pydantic Models ---
class UserCreate(BaseModel):
    username: str
    email: EmailStr
    password: str

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class TransportRequest(BaseModel):
    origin: str
    destination: str
    distance: Optional[float] = None
    predicted_delay: Optional[float] = None
    traffic_level: Optional[float] = None
    weather_score: Optional[float] = None

class SmartTransportRequest(BaseModel):
    distance: float
    traffic_level: float
    weather_score: float

class Stop(BaseModel):
    address: str

class OptimizeRequest(BaseModel):
    start: Stop
    stops: list[Stop]

class DelayRequest(BaseModel):
    origin: str
    destination: str
    timestamp: str
    origin_lat: Optional[float] = None
    origin_lon: Optional[float] = None

# --- User Helper Functions ---
def verify_password(plain_password, hashed_password):
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))

def get_password_hash(password):
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

# --- API Endpoints ---

# Root endpoint to serve the frontend
@app.get("/")
async def read_index():
    return FileResponse('frontend/index.html')

@app.post("/signup/", status_code=status.HTTP_201_CREATED)
def signup_user(user: UserCreate):
    """Handles user registration."""
    with engine.connect() as connection:
        user_exists_query = text("SELECT id FROM users WHERE email = :email")
        existing_user = connection.execute(user_exists_query, {"email": user.email}).fetchone()
        if existing_user:
            raise HTTPException(status_code=400, detail="Email already registered.")

        hashed_password = get_password_hash(user.password)
        
        insert_query = text("""
            INSERT INTO users (username, email, hashed_password)
            VALUES (:username, :email, :hashed_password)
            RETURNING id;
        """)
        try:
            new_user = connection.execute(insert_query, {
                "username": user.username,
                "email": user.email,
                "hashed_password": hashed_password
            }).fetchone()
            connection.commit()
            return {"message": "User created successfully!", "user_id": new_user[0]}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Database error: {e}")

@app.post("/login/")
def login_user(form_data: UserLogin):
    """Handles user login."""
    with engine.connect() as connection:
        query = text("SELECT * FROM users WHERE email = :email")
        user = connection.execute(query, {"email": form_data.email}).fetchone()

        if not user or not verify_password(form_data.password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        return {"message": "Login successful!", "username": user.username}

import re

def parse_duration_to_mins(duration_str):
    if not isinstance(duration_str, str): return 0
    h = 0; m = 0
    hr_match = re.search(r'(\d+)\s*(?:hour|h|hr|hours)', duration_str.lower())
    min_match = re.search(r'(\d+)\s*(?:minute|m|min|minutes)', duration_str.lower())
    if hr_match: h = int(hr_match.group(1))
    if min_match: m = int(min_match.group(1))
    return h * 60 + m

def format_mins_to_str(total_mins):
    h = int(total_mins // 60)
    m = int(total_mins % 60)
    if h > 0 and m > 0: return f"{h}h {m}m"
    if h > 0: return f"{h}h"
    return f"{m}m"

@app.post("/find-transport/")
def find_transport_options(req: TransportRequest):
    """Finds transport options from the database and dynamically enhances them."""
    # Ensure real distance and delay are populated
    req_dist = req.distance
    req_delay = req.predicted_delay
    if req_dist in (None, 0.0):
        try:
            o_lat, o_lon = geocode_place(req.origin)
            d_lat, d_lon = geocode_place(req.destination)
            if o_lat and d_lat:
                _, traf_sec, d_km, _ = get_route_info((o_lat, o_lon), (d_lat, d_lon))
                req_dist = d_km
                if req_delay in (None, 0.0):
                    req_delay = traf_sec / 60.0
        except Exception:
            pass

    dist = req_dist or 0.0
    delay = req_delay or 0.0
    traffic = req.traffic_level or 0.0
    weather = req.weather_score or 1.0

    with engine.connect() as connection:
        query = text("""
            SELECT * FROM transport_options
            WHERE origin_city ILIKE :origin AND destination_city ILIKE :destination;
        """)
        try:
            results = connection.execute(query, {"origin": f"%{req.origin}%", "destination": f"%{req.destination}%"}).fetchall()
            db_options = [dict(row._mapping) for row in results]
            
            enhanced_options = []
            
            # Map booking URLs
            booking_map = {
                "train": "https://www.irctc.co.in",
                "bus": "https://www.redbus.in",
                "cab": "https://m.uber.com",
                "flight": "https://www.makemytrip.com"
            }
            comfort_map = { "flight": 1.0, "train": 0.8, "cab": 0.6, "bus": 0.5 }
            
            max_price, max_time, max_delay = 1, 1, 1 # Prevent ZeroDivisionError
            raw_options = []
            
            for opt in db_options:
                t_type = str(opt.get("transport_type", "")).lower().strip()
                base_price = float(opt.get("fare", 500))
                db_time_mins = parse_duration_to_mins(opt.get("duration", "0m"))
                
                # OVERRIDE: Prevent DB anomalies (like 20h for Dehradun to Meerut) by calculating physics layout based on real distance
                base_time_mins = db_time_mins
                if dist > 0:
                    if t_type == "bus":
                        base_time_mins = (dist / 50) * 60
                    elif t_type == "cab":
                        base_time_mins = (dist / 60) * 60
                    elif t_type == "train":
                        base_time_mins = (dist / 80) * 60
                    elif t_type == "flight":
                        base_time_mins = (dist / 500) * 60
                        
                    # Apply sanity check to fare using real distance
                    if t_type == "cab" and base_price < dist * 10:
                        base_price = dist * 10
                    elif t_type == "bus" and base_price < dist * 1.2:
                        base_price = dist * 1.2
                    elif t_type == "train" and base_price < dist * 0.8:
                        base_price = dist * 0.8

                # Default assumptions for the step
                price = base_price
                time = base_time_mins
                available = True
                
                # Step 2: DYNAMIC PRICING AND TIMING ENHANCEMENT
                if t_type == "cab":
                    price = base_price + (dist * 12) + (traffic * 20)
                    time = base_time_mins + delay
                elif t_type == "bus":
                    price = base_price + (weather * 10)
                    time = base_time_mins + (delay * 1.2)
                elif t_type == "train":
                    price = base_price
                    time = base_time_mins + (delay * 0.5)
                elif t_type == "flight":
                    price = base_price + (dist * 2)
                    time = base_time_mins + 120 # 2 hour airport overhead
                    
                # Step 3: AVAILABILITY LOGIC
                warning_message = None
                if dist < 300 and t_type == "flight":
                    available = False
                if weather > 7 and t_type == "bus":
                    available = False
                if traffic > 8 and t_type == "cab":
                    warning_message = "High delay warning"
                
                # We only keep available options
                if available:
                    raw_opt = {
                        "type": t_type,
                        "operator": opt.get("operator_name", t_type.title()),
                        "price": round(price, 2),
                        "time_mins": time,
                        "time": format_mins_to_str(time),
                        "available": available,
                        "booking_link": booking_map.get(t_type, ""),
                        "warning": warning_message,
                        "comfort": comfort_map.get(t_type, 0.5),
                        "delay_applied": delay
                    }
                    raw_options.append(raw_opt)
                    
                    if raw_opt["price"] > max_price: max_price = raw_opt["price"]
                    if raw_opt["time_mins"] > max_time: max_time = raw_opt["time_mins"]
                    if raw_opt["delay_applied"] > max_delay: max_delay = raw_opt["delay_applied"]
            
            # Step 4: SCORING SYSTEM & TAGS
            for opt in raw_options:
                norm_time = opt["time_mins"] / max_time
                norm_price = opt["price"] / max_price
                norm_delay = opt["delay_applied"] / max_delay if max_delay > 0 else 0
                
                # We want LOW price, LOW time, LOW delay to have LOW score 
                # (Lower score = Better Option as per requirement: "Select lowest score as Best Option").
                # Note: Higher comfort should technically LOWER the score.
                # In requirement: (0.4 * norm_time) + (0.3 * norm_price) + (0.2 * norm_delay) + (0.1 * comfort)
                # If comfort is high (1.0), it ADDS to the score... That makes flight score worse. 
                # Let's subtract comfort from the penalty or define comfort_penalty = (1 - comfort). 
                # Since Prompt strictly says: `(0.4 * normalized_time) + (0.3 * normalized_price) + (0.2 * normalized_delay) + (0.1 * comfort_factor)`
                # I will adhere strictly to algorithmic formula exactly as provided.
                
                opt["score"] = round((0.4 * norm_time) + (0.3 * norm_price) + (0.2 * norm_delay) + (0.1 * opt["comfort"]), 3)
            
            # Sort by lowest score
            enhanced_options = sorted(raw_options, key=lambda x: x["score"])
            
            if enhanced_options:
                # Assign Tags
                enhanced_options[0]["recommendation"] = "Best Option"
                
                # Cheapest
                cheapest_opt = min(enhanced_options, key=lambda x: x["price"])
                cheapest_opt["tag"] = "Cheapest"
                
                # Fastest
                fastest_opt = min(enhanced_options, key=lambda x: x["time_mins"])
                if fastest_opt.get("tag"):
                    fastest_opt["tag"] += ", Fastest"
                else:
                    fastest_opt["tag"] = "Fastest"
                
            return enhanced_options
            
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Database error: {e}")

@app.post("/smart-recommend/")
def smart_recommend(req: SmartTransportRequest):
    """Smart transport recommendation engine using deterministic realtime logic."""
    distance = req.distance
    traffic_level = req.traffic_level
    weather_score = req.weather_score

    # Step 1: Base profiles
    profiles = {
        "bike":   {"speed": 40,  "cost": 1, "risk": 3},
        "car":    {"speed": 60,  "cost": 3, "risk": 2},
        "bus":    {"speed": 50,  "cost": 2, "risk": 2},
        "train":  {"speed": 80,  "cost": 3, "risk": 1},
        "flight": {"speed": 500, "cost": 5, "risk": 1}
    }

    results = []

    for t_type, base in profiles.items():
        base_speed = base["speed"]
        base_cost = base["cost"]
        base_risk = base["risk"]

        # 1. SPEED
        if t_type in ("bike", "car", "bus"):
            speed = base_speed * (1 - traffic_level * 0.05)
        else:
            speed = base_speed

        if weather_score > 6 and t_type in ("bike", "bus"):
            speed *= 0.8
        
        # Prevent zero division logic
        speed = max(speed, 1.0)

        # 2. TIME
        time = distance / speed
        if t_type == "flight":
            time += 2.0  # 2 hour airport overhead

        # 3. RISK
        risk = base_risk + (traffic_level * 0.2) + (weather_score * 0.2)
        if t_type == "bike" and weather_score > 6:
            risk += 2.0

        # 4. COST
        cost = base_cost + (distance * 0.01)

        results.append({
            "type": t_type,
            "time": time,
            "cost": cost,
            "risk": risk
        })

    # Step 3: Normalization
    max_time = max([r["time"] for r in results]) or 1.0
    max_cost = max([r["cost"] for r in results]) or 1.0
    max_risk = max([r["risk"] for r in results]) or 1.0

    # Step 4: Scoring
    for r in results:
        normalized_time = r["time"] / max_time
        normalized_cost = r["cost"] / max_cost
        normalized_risk = r["risk"] / max_risk
        
        r["score"] = (0.5 * normalized_time) + (0.3 * normalized_cost) + (0.2 * normalized_risk)

    # Step 5: Select Best + Backup
    sorted_results = sorted(results, key=lambda x: x["score"])
    best = sorted_results[0]
    backup = sorted_results[1]

    # Step 6: Generate Explanation Builder
    def get_reason(r_type):
        dist_cat = "Short distance" if distance < 50 else "Medium distance" if distance < 300 else "Long distance"
        
        if r_type == "train":
            return f"{dist_cat} with {'high' if traffic_level > 5 else 'moderate'} traffic makes train highly reliable and isolated from road delays."
        elif r_type == "flight":
            return f"{dist_cat} makes flight the overwhelmingly optimal choice to save time."
        elif r_type == "bike":
            return f"{dist_cat} with {'manageable' if traffic_level < 6 else 'heavy'} traffic makes a bike highly agile." + (" Warning: Poor weather increases risk." if weather_score > 6 else "")
        elif r_type == "bus":
            return f"A balanced option for {dist_cat.lower()} travel." + (" Expect delays due to poor weather." if weather_score > 6 else "")
        elif r_type == "car":
            return f"Offers unmatched flexibility for {dist_cat.lower()}, though susceptible to traffic fluctuations."
        return "A generally solid recommendation."

    # Step 7: Output structure
    return {
        "recommended": {
            "type": best["type"],
            "reason": get_reason(best["type"])
        },
        "backup": {
            "type": backup["type"],
            "reason": get_reason(backup["type"])
        }
    }

@app.post("/optimize-route/")
async def optimize_route_endpoint(req: OptimizeRequest):
    """Optimizes a multi-stop route using a genetic algorithm."""
    start_address = req.start.address
    destinations = [stop.address for stop in req.stops]
    
    place_names = [start_address] + destinations
    
    if len(place_names) < 2:
        raise HTTPException(status_code=400, detail="At least two stops (including start) are required for optimization.")
        
    optimized_locations = await find_optimal_route(place_names)
    
    # To draw the final route on the map, we need the full path
    full_route_path = []
    segment_tasks = []
    
    async with aiohttp.ClientSession() as session:
        for i in range(len(optimized_locations) - 1):
            origin_coords = (optimized_locations[i]['lat'], optimized_locations[i]['lon'])
            dest_coords = (optimized_locations[i+1]['lat'], optimized_locations[i+1]['lon'])
            segment_tasks.append(get_route_info_async(origin_coords, dest_coords, session))
        
        # Parallel fetch all segments of the final route
        results = await asyncio.gather(*segment_tasks)
        
        for _, _, _, path in results:
            if path:
                full_route_path.extend(path)

    return {"optimized_stops": optimized_locations, "route_path": full_route_path}


@app.get("/reverse-geocode/")
def reverse_geocode_api(lat: float, lon: float):
    address = reverse_geocode(lat, lon)
    if not address:
        raise HTTPException(status_code=404, detail="Could not find address.")
    return {"address": address}

@app.post("/predict-delay/")
async def predict_travel_delay(req: DelayRequest):
    """Predicts travel delay based on various factors."""
    if req.origin_lat is not None and req.origin_lon is not None:
        origin_lat, origin_lon = req.origin_lat, req.origin_lon
    else:
        origin_lat, origin_lon = geocode_place(req.origin)
        
    dest_lat, dest_lon = geocode_place(req.destination)

    if not all([origin_lat, origin_lon, dest_lat, dest_lon]):
        raise HTTPException(status_code=400, detail="Could not geocode origin or destination.")

    base_travel_sec, traffic_delay_sec, distance_km, route_path = get_route_info((origin_lat, origin_lon), (dest_lat, dest_lon))
    if base_travel_sec is None:
        raise HTTPException(status_code=500, detail="Could not calculate base route information.")

    # Convert departure timestamp to proper datetime format
    import datetime
    try:
        depart_dt = datetime.datetime.strptime(req.timestamp, "%Y-%m-%d %H:%M")
    except:
        depart_dt = datetime.datetime.now()

    segments = []
    weather_segments = []  # Detailed weather per chunk for the frontend
    NUM_CHUNKS = 6

    # 1. ROUTE SEGMENTATION
    # route_path contains list of (lat, lon)
    if route_path and len(route_path) >= NUM_CHUNKS + 1:
        # Pick NUM_CHUNKS+1 evenly spaced points along the path
        path_len = len(route_path)
        point_indices = [int(i * (path_len - 1) / NUM_CHUNKS) for i in range(NUM_CHUNKS + 1)]
        points = [route_path[idx] for idx in point_indices]
        
        chunk_duration_sec = base_travel_sec / NUM_CHUNKS
        chunk_labels = [f"Segment {i+1}" for i in range(NUM_CHUNKS)]

        # Build segment metadata
        seg_meta = []
        for i in range(NUM_CHUNKS):
            target_time = depart_dt + datetime.timedelta(seconds=(i + 1) * chunk_duration_sec)
            lat, lon = points[i+1]
            seg_meta.append({"i": i, "lat": lat, "lon": lon, "target_time": target_time})

        # PARALLEL: Fetch all weather forecasts + reverse geocode calls at once
        async with aiohttp.ClientSession() as session:
            weather_tasks = [
                async_get_combined_forecast(session, m["lat"], m["lon"], m["target_time"])
                for m in seg_meta
            ]
            geocode_tasks = [
                asyncio.to_thread(reverse_geocode, m["lat"], m["lon"])
                for m in seg_meta
            ]
            all_results = await asyncio.gather(*weather_tasks, *geocode_tasks)

        # Split results: first NUM_CHUNKS are weather, next NUM_CHUNKS are geocode
        weather_results = all_results[:NUM_CHUNKS]
        geocode_results = all_results[NUM_CHUNKS:]

        for i, m in enumerate(seg_meta):
            forecast = weather_results[i]
            seg_weather = forecast["weather_label"]
            detailed = forecast["detailed"]
            seg_location = geocode_results[i] or f"{m['lat']:.2f}, {m['lon']:.2f}"
            
            # Only first 3 segments feed into the ML model (model expects 3)
            if i < 3:
                segments.append({
                    "distance_km": distance_km / NUM_CHUNKS,
                    "traffic_level": normalize_traffic_delay(traffic_delay_sec),
                    "weather": seg_weather,
                    "timestamp_obj": m["target_time"]
                })

            weather_segments.append({
                "segment_number": i + 1,
                "segment_label": chunk_labels[i],
                "location": seg_location,
                "lat": m["lat"],
                "lon": m["lon"],
                "estimated_arrival": m["target_time"].strftime("%Y-%m-%d %H:%M"),
                "distance_km": round(distance_km / NUM_CHUNKS, 1),
                "severity": get_weather_severity(detailed.get("condition", "clear")),
                **detailed
            })
    else:
        # Fallback to simple unsegmented calculation if path is missing
        fallback_time = depart_dt + datetime.timedelta(seconds=base_travel_sec)
        seg_weather = get_forecast_by_coords(dest_lat, dest_lon, fallback_time)
        detailed = get_detailed_forecast_by_coords(dest_lat, dest_lon, fallback_time)

        segments.append({
            "distance_km": distance_km,
            "traffic_level": normalize_traffic_delay(traffic_delay_sec),
            "weather": seg_weather,
            "timestamp_obj": fallback_time
        })

        weather_segments.append({
            "segment_number": 1,
            "segment_label": "Full Route",
            "location": req.destination,
            "lat": dest_lat,
            "lon": dest_lon,
            "estimated_arrival": fallback_time.strftime("%Y-%m-%d %H:%M"),
            "distance_km": round(distance_km, 1),
            "severity": get_weather_severity(detailed.get("condition", "clear")),
            **detailed
        })

    predicted_delay, confidence, final_weather_score = predict_route_segments(segments)
    
    base_travel_minutes = base_travel_sec / 60
    total_time = base_travel_minutes + predicted_delay

    return {
        "base_travel_minutes": base_travel_minutes,
        "predicted_delay_minutes": predicted_delay,
        "total_estimated_time": total_time,
        "weather": segments[-1]["weather"] if segments else get_weather(req.destination),
        "weather_score": final_weather_score,
        "weather_segments": weather_segments,
        "traffic_level": normalize_traffic_delay(traffic_delay_sec),
        "confidence_score": confidence,
        "distance_km": distance_km,
        "stops": [
            {"name": req.origin, "lat": origin_lat, "lon": origin_lon},
            {"name": req.destination, "lat": dest_lat, "lon": dest_lon}
        ],
        "route_path": route_path
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)