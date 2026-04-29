"""
Cost matrix uses real TomTom road travel times via parallel API calls. 
Haversine is fallback only.
"""

import random
import asyncio
import time
import math
from typing import List, Dict, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import lru_cache

from backend.tomtom_api import get_route_info, geocode_place

# --- STEP 1: Geocoding (Parallel) ---

@lru_cache(maxsize=256)
def cached_geocode(place_name: str) -> Tuple[Optional[float], Optional[float]]:
    """Caches geocoding results to save API tokens."""
    return geocode_place(place_name)

def geocode_all(place_names: List[str]) -> List[Dict]:
    """Geocodes all place names concurrently."""
    results = {}
    
    def fetch(i, name):
        # Pace geocoding calls to avoid 429s
        time.sleep(i * 0.05)
        lat, lon = cached_geocode(name)
        return i, name, lat, lon
    
    with ThreadPoolExecutor(max_workers=min(16, len(place_names))) as ex:
        futures = [ex.submit(fetch, i, name) for i, name in enumerate(place_names)]
        for f in as_completed(futures):
            i, name, lat, lon = f.result()
            results[i] = (name, lat, lon)
    
    return [
        {"name": results[i][0], "lat": results[i][1], "lon": results[i][2]}
        for i in sorted(results)
        if results[i][1] is not None
    ]

# --- STEP 2: Real Road Cost Matrix (Parallel TomTom calls) ---

def haversine_minutes(lat1: float, lon1: float, lat2: float, lon2: float, speed_kmph: float = 35.0) -> float:
    """Fallback only — used when TomTom API call fails (Traffic-aware 35km/h avg)."""
    R = 6371 # Radius of Earth in km
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = (math.sin(dphi/2)**2 + 
         math.cos(phi1) * math.cos(phi2) * math.sin(dlambda/2)**2)
    km = R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    # Approximation: Add 30% for road turns and divide by avg city speed
    return (km * 1.3 / speed_kmph) * 60 

def compute_cost_matrix(locations: List[Dict]) -> List[List[float]]:
    """Builds the cost matrix using ACTUAL road travel times from TomTom API."""
    n = len(locations)
    cost_matrix = [[0.0] * n for _ in range(n)]
    
    pairs = [(i, j) for i in range(n) for j in range(n) if i != j]
    
    def fetch_road_time(i, j):
        origin = (locations[i]['lat'], locations[i]['lon'])
        dest = (locations[j]['lat'], locations[j]['lon'])
        
        # Rate limit safety: add a tiny staggered delay
        time.sleep(0.1)
        
        # get_route_info returns (base_sec, delay_sec, dist_km, path)
        res = get_route_info(origin, dest)
        travel_time_sec = res[0] # Base travel time in seconds
        
        if travel_time_sec:
            # Add traffic delay if available (res[1])
            total_time_sec = travel_time_sec + (res[1] or 0)
            return i, j, total_time_sec / 60.0 # convert to minutes
        else:
            # Fallback to Haversine ONLY if TomTom fails
            fallback = haversine_minutes(
                locations[i]['lat'], locations[i]['lon'],
                locations[j]['lat'], locations[j]['lon']
            )
            return i, j, fallback

    # Call TomTom in parallel to build the matrix quickly
    with ThreadPoolExecutor(max_workers=min(32, len(pairs))) as ex:
        futures = [ex.submit(fetch_road_time, i, j) for i, j in pairs]
        for f in as_completed(futures):
            i, j, cost = f.result()
            cost_matrix[i][j] = cost
            
    return cost_matrix

# --- STEP 3 & 4: Genetic Algorithm with Greedy Seed ---

def greedy_seed(cost_matrix: List[List[float]], start: int = 0) -> List[int]:
    """Builds the initial population seed using nearest neighbor on the REAL cost matrix."""
    n = len(cost_matrix)
    unvisited = set(range(n))
    unvisited.remove(start)
    route = [start]
    current = start
    
    while unvisited:
        nearest = min(unvisited, key=lambda j: cost_matrix[current][j])
        route.append(nearest)
        unvisited.remove(nearest)
        current = nearest
    
    return route

def route_cost(route: List[int], cost_matrix: List[List[float]]) -> float:
    """Calculates the total travel time of a route."""
    return sum(cost_matrix[route[i]][route[i+1]] for i in range(len(route)-1))

def genetic_algorithm(cost_matrix: List[List[float]]) -> List[int]:
    """Optimizes route sequence using a Genetic Algorithm with real road times."""
    n = len(cost_matrix)
    if n <= 2:
        return list(range(n)) + [0] if n > 1 else [0]

    # Adaptive parameters (Maximized for absolute accuracy)
    if n <= 4:
        population_size, generations = 50, 60
    elif n <= 8:
        population_size, generations = 100, 150
    elif n <= 15:
        population_size, generations = 200, 300
    else:
        population_size, generations = 300, 500

    def create_individual():
        ind = list(range(1, n))
        random.shuffle(ind)
        return [0] + ind

    def mutate(ind):
        if n - 1 < 2: return
        a, b = random.sample(range(1, n), 2)
        ind[a], ind[b] = ind[b], ind[a]

    def crossover(p1, p2):
        if n - 1 < 2: return p1[:]
        child = [-1] * len(p1)
        start, end = sorted(random.sample(range(1, n), 2))
        child[start:end] = p1[start:end]
        
        pointer = 1
        for gene in p2[1:]:
            if gene not in child:
                while child[pointer] != -1:
                    pointer += 1
                child[pointer] = gene
        return [0] + child[1:]

    # Initial Population
    population = [create_individual() for _ in range(population_size)]
    
    # SEEDING: Use Greedy Nearest Neighbor for the first individual
    population[0] = greedy_seed(cost_matrix, start=0)

    best_cost = float('inf')
    no_improvement_count = 0
    patience = 15 # Generations without improvement before early stopping

    for _ in range(generations):
        # Calculate fitness for OPEN PATH (Minimize cost from p0 to pn)
        population.sort(key=lambda x: route_cost(x, cost_matrix))
        current_best_cost = route_cost(population[0], cost_matrix)

        if current_best_cost < best_cost:
            best_cost = current_best_cost
            no_improvement_count = 0
        else:
            no_improvement_count += 1
        
        if no_improvement_count >= patience:
            break
            
        # Elitism: Keep top 2
        next_gen = population[:2]
        
        # ADAPTIVE MUTATION: Increase risk if we're not improving
        mutation_rate = 0.3 if no_improvement_count < 5 else 0.6
        
        while len(next_gen) < population_size:
            p1, p2 = random.sample(population[:len(population)//2], 2)
            child = crossover(p1, p2)
            if random.random() < mutation_rate:
                mutate(child)
            next_gen.append(child)
        population = next_gen
        
    return population[0] # Returns [0, p1, ..., pn]

# --- STEP 5: 2-Opt Refinement (with memoized cost) ---

def two_opt(route: List[int], cost_matrix: List[List[float]]) -> List[int]:
    """Iteratively improves the route by untangling crossings (Local Search)."""
    best = route[:]
    best_cost = route_cost(best, cost_matrix)
    improved = True
    
    while improved:
        improved = False
        # loop i from 1 to n-1 (fixed start)
        for i in range(1, len(best)):
            # loop j from i+1 to end (allowing reversals that change the tail)
            for j in range(i + 1, len(best) + 1):
                if j - i <= 1:
                    continue
                new_route = best[:]
                new_route[i:j] = best[i:j][::-1]
                new_cost = route_cost(new_route, cost_matrix)
                if new_cost < best_cost:
                    best = new_route
                    best_cost = new_cost
                    improved = True
    return best

# --- FINAL INTERFACES ---

def optimize_route(place_names: List[str]) -> List[Dict]:
    """Synchronous version for router.py."""
    import asyncio
    # Since find_optimal_route is async, we can run it in a loop if needed, 
    # but here we'll just implement the logic directly to avoid loop issues.
    start_time_total = time.time()
    
    # 1. Geocoding
    locations = geocode_all(place_names)
    if len(locations) < 2:
        return locations

    # 2. Matrix Generation (Parallel TomTom)
    matrix_start = time.time()
    cost_matrix = compute_cost_matrix(locations)
    print(f"[PERF] Real Road Matrix Generation: {time.time() - matrix_start:.2f}s")
    
    # 3. GA Execution
    ga_start = time.time()
    best_indices = genetic_algorithm(cost_matrix)
    
    # 4. 2-opt refinement
    if len(best_indices) > 3:
        best_indices = two_opt(best_indices, cost_matrix)
    
    print(f"[PERF] Total Optimization (GA + 2-opt): {time.time() - ga_start:.2f}s")
    print(f"[PERF] Overall optimization time: {time.time() - start_time_total:.2f}s")

    # 5. Return in original format (now already optimized as open path)
    return [locations[i] for i in best_indices]

async def find_optimal_route(place_names: List[str]) -> List[Dict]:
    """Asynchronous version for main.py."""
    # Since our matrix generation uses ThreadPoolExecutor, 
    # we can run the whole thing in a thread to avoid blocking the event loop.
    return await asyncio.to_thread(optimize_route, place_names)