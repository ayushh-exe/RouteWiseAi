import random
from backend.tomtom_api import get_route_info, geocode_place

def compute_cost_matrix(locations):
    n = len(locations)
    cost_matrix = [[0]*n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            if i != j:
                origin_coords = (locations[i]['lat'], locations[i]['lon'])
                dest_coords = (locations[j]['lat'], locations[j]['lon'])
                time, _ = get_route_info(origin_coords, dest_coords)
                cost_matrix[i][j] = time or 999999
    return cost_matrix

def route_cost(route, cost_matrix):
    return sum(cost_matrix[route[i]][route[i+1]] for i in range(len(route)-1))

def two_opt(route, cost_matrix):
    best = route
    improved = True
    while improved:
        improved = False
        for i in range(1, len(route) - 2):
            for j in range(i + 1, len(route)):
                if j - i == 1:
                    continue
                new_route = best[:]
                new_route[i:j] = best[j - 1:i - 1:-1]
                if route_cost(new_route, cost_matrix) < route_cost(best, cost_matrix):
                    best = new_route
                    improved = True
        route = best
    return best

def genetic_algorithm(cost_matrix, population_size=30, generations=50):
    n = len(cost_matrix)
    

    if n <= 2:
        return list(range(n)) + [0] if n > 1 else [0]

    def create_individual():
        ind = list(range(1, n))
        random.shuffle(ind)
        return [0] + ind

    def mutate(ind):

        if n - 1 < 2:
            return
        a, b = random.sample(range(1, n), 2)
        ind[a], ind[b] = ind[b], ind[a]

    def crossover(p1, p2):

        if n - 1 < 2:
            return p1[:]
            
        child = [-1]*len(p1)

        start, end = sorted(random.sample(range(1, n), 2))
        child[start:end] = p1[start:end]
        
        pointer = 1
        for gene in p2[1:]: 
            if gene not in child:
                # Find the next available spot in the child
                while child[pointer] != -1:
                    pointer += 1
                child[pointer] = gene
        return [0] + child[1:]

    population = [create_individual() for _ in range(population_size)]
    
    for _ in range(generations):
        # Add the return to origin (index 0) for accurate cost calculation
        population.sort(key=lambda x: route_cost(x + [0], cost_matrix))
        
        # Elitism: Keep the top 10%
        next_gen = population[:max(1, population_size // 10)]

        while len(next_gen) < population_size:
            # Select parents from the top 50% of the current generation
            p1, p2 = random.sample(population[:len(population)//2], 2)
            child = crossover(p1, p2)
            if random.random() < 0.3: 
                mutate(child)
            next_gen.append(child)
        population = next_gen
    
    # Return the best route, including the return to origin for 2-opt
    best_route_open = population[0]
    return best_route_open + [0]


def optimize_route(place_names):
    locations = []
    for name in place_names:
        lat, lon = geocode_place(name)
        if lat is not None and lon is not None:
            locations.append({"name": name, "lat": lat, "lon": lon})
    
    if len(locations) < 2:
        return locations

    cost_matrix = compute_cost_matrix(locations)
    
    best_indices_with_return = genetic_algorithm(cost_matrix)
    
    # Only run 2-opt if there are enough points to optimize
    if len(best_indices_with_return) > 3:
        best_indices_with_return = two_opt(best_indices_with_return, cost_matrix)

    # Remove the last stop (return to origin) before sending to frontend
    optimized_locations = [locations[i] for i in best_indices_with_return[:-1]]
    
    return optimized_locations
