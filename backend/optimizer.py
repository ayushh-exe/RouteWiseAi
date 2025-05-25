import random
from backend.tomtom_api import get_route_info

def compute_cost_matrix(place_names):
    n = len(place_names)
    cost_matrix = [[0]*n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            if i != j:
                time, _ = get_route_info(place_names[i], place_names[j])
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
    def create_individual():
        ind = list(range(1, n))
        random.shuffle(ind)
        return [0] + ind + [0]
    def mutate(ind):
        a, b = random.sample(range(1, n), 2)
        ind[a], ind[b] = ind[b], ind[a]
    def crossover(p1, p2):
        child = [-1]*len(p1)
        start, end = sorted(random.sample(range(1, n), 2))
        child[start:end] = p1[start:end]
        pointer = 1
        for gene in p2[1:-1]:
            if gene not in child:
                while child[pointer] != -1:
                    pointer += 1
                child[pointer] = gene
        return [0] + child[1:-1] + [0]

    population = [create_individual() for _ in range(population_size)]
    for _ in range(generations):
        population.sort(key=lambda x: route_cost(x, cost_matrix))
        next_gen = population[:10]
        while len(next_gen) < population_size:
            p1, p2 = random.sample(population[:20], 2)
            child = crossover(p1, p2)
            if random.random() < 0.3:
                mutate(child)
            next_gen.append(child)
        population = next_gen
    return population[0]

def optimize_route(place_names):
    cost_matrix = compute_cost_matrix(place_names)
    best = genetic_algorithm(cost_matrix)
    best = two_opt(best, cost_matrix)
    return [place_names[i] for i in best]
