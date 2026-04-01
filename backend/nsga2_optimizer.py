"""
NSGA-II Multi-Objective Genetic Algorithm Optimizer for GreenPath.
Optimizes flight paths across three objectives: CO₂, contrail energy forcing, and time.
"""
import numpy as np
from typing import List, Tuple, Dict
import copy

from fuel_model import (
    AIRCRAFT, ALTITUDE_BANDS, altitude_band_to_ft, altitude_band_to_pressure,
    haversine_distance_km, compute_bearing, wind_component_along_track,
    compute_segment_fuel, CO2_PER_KG_FUEL
)
from issr_detector import get_issr_at_point, get_wind_at_point


# ----- Great Circle Utilities -----

def great_circle_waypoints(lat1: float, lon1: float, lat2: float, lon2: float, n: int = 20) -> list:
    """Generate n equally-spaced waypoints along the great circle arc."""
    lat1_r, lon1_r = np.radians(lat1), np.radians(lon1)
    lat2_r, lon2_r = np.radians(lat2), np.radians(lon2)

    d = 2 * np.arcsin(np.sqrt(
        np.sin((lat2_r - lat1_r) / 2) ** 2 +
        np.cos(lat1_r) * np.cos(lat2_r) * np.sin((lon2_r - lon1_r) / 2) ** 2
    ))

    if d < 1e-10:
        return [(lat1, lon1)] * n

    waypoints = []
    for i in range(n):
        f = i / (n - 1) if n > 1 else 0
        a = np.sin((1 - f) * d) / np.sin(d)
        b = np.sin(f * d) / np.sin(d)
        x = a * np.cos(lat1_r) * np.cos(lon1_r) + b * np.cos(lat2_r) * np.cos(lon2_r)
        y = a * np.cos(lat1_r) * np.sin(lon1_r) + b * np.cos(lat2_r) * np.sin(lon2_r)
        z = a * np.sin(lat1_r) + b * np.sin(lat2_r)
        lat = np.degrees(np.arctan2(z, np.sqrt(x ** 2 + y ** 2)))
        lon = np.degrees(np.arctan2(y, x))
        waypoints.append((lat, lon))
    return waypoints


def interpolate_path(waypoints: list, points_per_segment: int = 5) -> list:
    """Interpolate sparse waypoints for smooth rendering."""
    if len(waypoints) < 2:
        return waypoints
    result = []
    for i in range(len(waypoints) - 1):
        lat1, lon1, alt1 = waypoints[i]
        lat2, lon2, alt2 = waypoints[i + 1]
        gc = great_circle_waypoints(lat1, lon1, lat2, lon2, points_per_segment + 1)
        for j, (lat, lon) in enumerate(gc):
            if i > 0 and j == 0:
                continue
            f = j / points_per_segment
            alt = alt1 + f * (alt2 - alt1)
            result.append((lat, lon, int(round(alt))))
    return result


# ----- Objective Functions -----

def rf_weight(local_hour: float, lat: float) -> float:
    """Radiative forcing weight: day/night factor for contrail warming effect."""
    # Contrails warm more during the day (solar reflection) vs night (IR only)
    # Day peak at noon: 1.3, Night trough: 0.7
    day_factor = 0.7 + 0.6 * max(0, np.cos(np.radians((local_hour - 12) * 15)))
    # Higher latitudes in summer have longer days
    lat_factor = 1.0 + 0.1 * abs(lat) / 90.0
    return day_factor * lat_factor


def f1_co2(waypoints: list, aircraft_type: str, atmo_data: dict) -> float:
    """Objective 1: Total CO₂ emissions (kg), wind-corrected."""
    total_co2 = 0.0
    ac = AIRCRAFT[aircraft_type]
    for i in range(len(waypoints) - 1):
        lat1, lon1, alt1 = waypoints[i]
        lat2, lon2, alt2 = waypoints[i + 1]
        u_w, v_w = get_wind_at_point((lat1 + lat2) / 2, (lon1 + lon2) / 2,
                                      int((alt1 + alt2) / 2), atmo_data)
        seg = compute_segment_fuel(lat1, lon1, lat2, lon2, aircraft_type, u_w, v_w)
        total_co2 += seg["co2_kg"]
    return total_co2


def f2_contrail_ef(waypoints: list, atmo_data: dict, departure_hour: float = 12.0) -> float:
    """Objective 2: Contrail energy forcing (arbitrary units)."""
    total_ef = 0.0
    for i in range(len(waypoints) - 1):
        lat1, lon1, alt1 = waypoints[i]
        lat2, lon2, alt2 = waypoints[i + 1]
        mid_lat = (lat1 + lat2) / 2
        mid_lon = (lon1 + lon2) / 2
        mid_alt = int((alt1 + alt2) / 2)

        issr = get_issr_at_point(mid_lat, mid_lon, mid_alt, atmo_data)
        seg_length = haversine_distance_km(lat1, lon1, lat2, lon2)

        # Estimate local time offset
        local_hour = (departure_hour + mid_lon / 15.0) % 24
        rfw = rf_weight(local_hour, mid_lat)

        total_ef += issr * seg_length * rfw
    return total_ef


def f3_time(waypoints: list, aircraft_type: str, atmo_data: dict) -> float:
    """Objective 3: Total flight time (minutes), wind-corrected."""
    total_time = 0.0
    ac = AIRCRAFT[aircraft_type]
    for i in range(len(waypoints) - 1):
        lat1, lon1, alt1 = waypoints[i]
        lat2, lon2, alt2 = waypoints[i + 1]
        u_w, v_w = get_wind_at_point((lat1 + lat2) / 2, (lon1 + lon2) / 2,
                                      int((alt1 + alt2) / 2), atmo_data)
        seg = compute_segment_fuel(lat1, lon1, lat2, lon2, aircraft_type, u_w, v_w)
        total_time += seg["time_s"]
    return total_time / 60.0


# ----- NSGA-II Core -----

def evaluate(individual: list, aircraft_type: str, atmo_data: dict, dep_hour: float) -> Tuple[float, float, float]:
    """Evaluate all three objectives for an individual."""
    co2 = f1_co2(individual, aircraft_type, atmo_data)
    ef = f2_contrail_ef(individual, atmo_data, dep_hour)
    time_min = f3_time(individual, aircraft_type, atmo_data)
    return (co2, ef, time_min)


def dominates(a: Tuple, b: Tuple) -> bool:
    """Check if solution a dominates solution b (all objectives minimized)."""
    return all(ai <= bi for ai, bi in zip(a, b)) and any(ai < bi for ai, bi in zip(a, b))


def non_dominated_sort(fitness_list: List[Tuple]) -> List[List[int]]:
    """Fast non-dominated sort (Deb 2002). Returns list of fronts."""
    n = len(fitness_list)
    domination_count = [0] * n
    dominated_set = [[] for _ in range(n)]
    fronts = [[]]

    for i in range(n):
        for j in range(i + 1, n):
            if dominates(fitness_list[i], fitness_list[j]):
                dominated_set[i].append(j)
                domination_count[j] += 1
            elif dominates(fitness_list[j], fitness_list[i]):
                dominated_set[j].append(i)
                domination_count[i] += 1

    for i in range(n):
        if domination_count[i] == 0:
            fronts[0].append(i)

    k = 0
    while fronts[k]:
        next_front = []
        for i in fronts[k]:
            for j in dominated_set[i]:
                domination_count[j] -= 1
                if domination_count[j] == 0:
                    next_front.append(j)
        k += 1
        fronts.append(next_front)

    return [f for f in fronts if f]


def crowding_distance(front_indices: List[int], fitness_list: List[Tuple]) -> Dict[int, float]:
    """Calculate crowding distance for a front."""
    if len(front_indices) <= 2:
        return {i: float('inf') for i in front_indices}

    n_obj = len(fitness_list[0])
    distances = {i: 0.0 for i in front_indices}

    for m in range(n_obj):
        sorted_front = sorted(front_indices, key=lambda i: fitness_list[i][m])
        distances[sorted_front[0]] = float('inf')
        distances[sorted_front[-1]] = float('inf')

        obj_range = fitness_list[sorted_front[-1]][m] - fitness_list[sorted_front[0]][m]
        if obj_range < 1e-10:
            continue

        for k in range(1, len(sorted_front) - 1):
            distances[sorted_front[k]] += (
                fitness_list[sorted_front[k + 1]][m] - fitness_list[sorted_front[k - 1]][m]
            ) / obj_range

    return distances


def tournament_select(population: list, ranks: dict, crowd_dist: dict) -> list:
    """Binary tournament selection."""
    n = len(population)
    i, j = np.random.randint(0, n), np.random.randint(0, n)
    while i == j:
        j = np.random.randint(0, n)

    # Prefer lower rank (better front)
    if ranks[i] < ranks[j]:
        return copy.deepcopy(population[i])
    elif ranks[j] < ranks[i]:
        return copy.deepcopy(population[j])
    # Same rank -> prefer higher crowding distance
    elif crowd_dist.get(i, 0) > crowd_dist.get(j, 0):
        return copy.deepcopy(population[i])
    else:
        return copy.deepcopy(population[j])


def crossover(parent1: list, parent2: list, rate: float = 0.9) -> Tuple[list, list]:
    """Single-point crossover on waypoint sequences."""
    if np.random.random() > rate or len(parent1) < 3 or len(parent2) < 3:
        return copy.deepcopy(parent1), copy.deepcopy(parent2)

    # Keep first and last waypoints fixed (origin/destination)
    inner1 = parent1[1:-1]
    inner2 = parent2[1:-1]

    # Pad to same length
    max_len = max(len(inner1), len(inner2))
    while len(inner1) < max_len:
        inner1.append(inner1[-1])
    while len(inner2) < max_len:
        inner2.append(inner2[-1])

    point = np.random.randint(1, max_len)
    child1_inner = inner1[:point] + inner2[point:]
    child2_inner = inner2[:point] + inner1[point:]

    child1 = [parent1[0]] + child1_inner + [parent1[-1]]
    child2 = [parent2[0]] + child2_inner + [parent2[-1]]

    return child1, child2


def mutate(chromosome: list, rate: float = 0.2, atmo_data: dict = None) -> list:
    """
    Mutate a chromosome with three mutation types:
    1. Perturb waypoint position (±2° lat/lon)
    2. Shift altitude band ±1
    3. Insert or delete a waypoint
    + Smart mutation: nudge away from high ISSR zones
    """
    if np.random.random() > rate:
        return chromosome

    chrom = copy.deepcopy(chromosome)

    if len(chrom) < 3:
        return chrom

    mutation_type = np.random.randint(0, 3)

    if mutation_type == 0:
        # Perturb waypoint position
        idx = np.random.randint(1, len(chrom) - 1)
        lat, lon, alt = chrom[idx]
        lat += np.random.uniform(-2, 2)
        lon += np.random.uniform(-2, 2)
        lat = np.clip(lat, -85, 85)
        lon = np.clip(lon, -180, 180)

        # Smart mutation: if in high ISSR zone, nudge more aggressively
        if atmo_data is not None:
            issr = get_issr_at_point(lat, lon, alt, atmo_data)
            if issr > 5.0:
                # Try shifting lat/lon more to escape ISSR
                best_lat, best_lon, best_issr = lat, lon, issr
                for _ in range(4):
                    test_lat = lat + np.random.uniform(-4, 4)
                    test_lon = lon + np.random.uniform(-4, 4)
                    test_lat = np.clip(test_lat, -85, 85)
                    test_lon = np.clip(test_lon, -180, 180)
                    test_issr = get_issr_at_point(test_lat, test_lon, alt, atmo_data)
                    if test_issr < best_issr:
                        best_lat, best_lon, best_issr = test_lat, test_lon, test_issr
                lat, lon = best_lat, best_lon

        chrom[idx] = (lat, lon, alt)

    elif mutation_type == 1:
        # Shift altitude band
        idx = np.random.randint(1, len(chrom) - 1)
        lat, lon, alt = chrom[idx]
        alt += np.random.choice([-1, 1])
        alt = np.clip(alt, 0, 3)

        # Smart: try both directions, pick lower ISSR
        if atmo_data is not None:
            issr_up = get_issr_at_point(lat, lon, min(alt + 1, 3), atmo_data) if alt < 3 else float('inf')
            issr_down = get_issr_at_point(lat, lon, max(alt - 1, 0), atmo_data) if alt > 0 else float('inf')
            issr_curr = get_issr_at_point(lat, lon, alt, atmo_data)
            if issr_up < issr_curr and issr_up < issr_down and alt < 3:
                alt = alt + 1
            elif issr_down < issr_curr and alt > 0:
                alt = alt - 1

        chrom[idx] = (lat, lon, int(alt))

    else:
        # Insert or delete a waypoint
        if len(chrom) > 4 and np.random.random() < 0.5:
            # Delete
            idx = np.random.randint(1, len(chrom) - 1)
            chrom.pop(idx)
        elif len(chrom) < 16:
            # Insert between two existing waypoints
            idx = np.random.randint(1, len(chrom) - 1)
            lat1, lon1, alt1 = chrom[idx - 1]
            lat2, lon2, alt2 = chrom[idx]
            new_lat = (lat1 + lat2) / 2 + np.random.uniform(-1, 1)
            new_lon = (lon1 + lon2) / 2 + np.random.uniform(-1, 1)
            new_alt = np.random.choice([alt1, alt2])
            chrom.insert(idx, (new_lat, new_lon, int(new_alt)))

    return chrom


def initialize_population(
    origin: Tuple[float, float],
    destination: Tuple[float, float],
    pop_size: int = 150,
    atmo_data: dict = None
) -> list:
    """Generate initial population of flight paths."""
    population = []

    # Add great circle baseline as first individual
    gc = great_circle_waypoints(origin[0], origin[1], destination[0], destination[1], 12)
    baseline = [(lat, lon, 2) for lat, lon in gc]  # altitude band 2 = 37000 ft
    population.append(baseline)

    for _ in range(pop_size - 1):
        n_waypoints = np.random.randint(8, 15)
        gc = great_circle_waypoints(origin[0], origin[1], destination[0], destination[1], n_waypoints)

        path = []
        for k, (lat, lon) in enumerate(gc):
            if k == 0 or k == len(gc) - 1:
                # Keep origin/destination roughly fixed
                alt = 2
                path.append((lat, lon, alt))
            else:
                # Perturb
                plat = lat + np.random.uniform(-8, 8)
                plon = lon + np.random.uniform(-8, 8)
                plat = np.clip(plat, -85, 85)
                plon = np.clip(plon, -180, 180)
                alt = np.random.randint(0, 4)
                path.append((plat, plon, alt))

        population.append(path)

    return population


def run_nsga2(
    origin: Tuple[float, float],
    destination: Tuple[float, float],
    aircraft_type: str,
    atmo_data: dict,
    departure_hour: float = 12.0,
    pop_size: int = 100,
    n_generations: int = 80,
) -> dict:
    """
    Run the full NSGA-II optimizer.
    
    Returns dict with:
        - pareto_front: list of {waypoints, co2_kg, contrail_ef, time_min, path_id}
        - all_fitness: list of (co2, ef, time) tuples for the final population
    """
    # Initialize
    population = initialize_population(origin, destination, pop_size, atmo_data)

    # Evaluate initial population
    fitness = []
    for ind in population:
        try:
            fit = evaluate(ind, aircraft_type, atmo_data, departure_hour)
            # Sanity check
            if any(np.isnan(f) or np.isinf(f) for f in fit):
                fit = (1e9, 1e9, 1e9)
        except Exception:
            fit = (1e9, 1e9, 1e9)
        fitness.append(fit)

    # Main loop
    for gen in range(n_generations):
        # Non-dominated sort
        fronts = non_dominated_sort(fitness)

        # Assign ranks and crowding distances
        ranks = {}
        all_crowd = {}
        for rank, front in enumerate(fronts):
            cd = crowding_distance(front, fitness)
            for idx in front:
                ranks[idx] = rank
                all_crowd[idx] = cd[idx]

        # Generate offspring
        offspring = []
        offspring_fitness = []

        while len(offspring) < pop_size:
            p1 = tournament_select(population, ranks, all_crowd)
            p2 = tournament_select(population, ranks, all_crowd)
            c1, c2 = crossover(p1, p2)
            c1 = mutate(c1, 0.2, atmo_data)
            c2 = mutate(c2, 0.2, atmo_data)
            offspring.append(c1)
            offspring.append(c2)

        # Evaluate offspring
        for ind in offspring:
            try:
                fit = evaluate(ind, aircraft_type, atmo_data, departure_hour)
                if any(np.isnan(f) or np.isinf(f) for f in fit):
                    fit = (1e9, 1e9, 1e9)
            except Exception:
                fit = (1e9, 1e9, 1e9)
            offspring_fitness.append(fit)

        # Combine parent + offspring
        combined = population + offspring[:pop_size]
        combined_fitness = fitness + offspring_fitness[:pop_size]

        # Non-dominated sort on combined
        combined_fronts = non_dominated_sort(combined_fitness)

        # Select next generation
        new_population = []
        new_fitness = []
        for front in combined_fronts:
            if len(new_population) + len(front) <= pop_size:
                for idx in front:
                    new_population.append(combined[idx])
                    new_fitness.append(combined_fitness[idx])
            else:
                # Need partial front — sort by crowding distance
                cd = crowding_distance(front, combined_fitness)
                sorted_front = sorted(front, key=lambda i: cd.get(i, 0), reverse=True)
                remaining = pop_size - len(new_population)
                for idx in sorted_front[:remaining]:
                    new_population.append(combined[idx])
                    new_fitness.append(combined_fitness[idx])
                break

        population = new_population
        fitness = new_fitness

    # Extract Pareto front (front 0)
    final_fronts = non_dominated_sort(fitness)
    pareto_indices = final_fronts[0] if final_fronts else list(range(len(population)))

    pareto_front = []
    for idx, i in enumerate(pareto_indices):
        pareto_front.append({
            "waypoints": population[i],
            "co2_kg": fitness[i][0],
            "contrail_ef": fitness[i][1],
            "time_min": fitness[i][2],
            "path_id": idx,
        })

    return {
        "pareto_front": pareto_front,
        "all_fitness": fitness,
        "population": population,
    }


def select_by_weights(
    pareto_front: list,
    weights: dict
) -> dict:
    """
    Select the solution closest to user preference weights.
    score = w_co2 * norm(co2) + w_contrail * norm(ef) + w_time * norm(time)
    """
    if not pareto_front:
        return None

    co2_vals = [p["co2_kg"] for p in pareto_front]
    ef_vals = [p["contrail_ef"] for p in pareto_front]
    time_vals = [p["time_min"] for p in pareto_front]

    co2_min, co2_max = min(co2_vals), max(co2_vals)
    ef_min, ef_max = min(ef_vals), max(ef_vals)
    time_min, time_max = min(time_vals), max(time_vals)

    co2_range = co2_max - co2_min if co2_max > co2_min else 1.0
    ef_range = ef_max - ef_min if ef_max > ef_min else 1.0
    time_range = time_max - time_min if time_max > time_min else 1.0

    w_co2 = weights.get("co2", 0.33)
    w_contrail = weights.get("contrail", 0.34)
    w_time = weights.get("time", 0.33)
    w_total = w_co2 + w_contrail + w_time
    if w_total > 0:
        w_co2 /= w_total
        w_contrail /= w_total
        w_time /= w_total

    best_score = float('inf')
    best_idx = 0

    for i, p in enumerate(pareto_front):
        score = (
            w_co2 * (p["co2_kg"] - co2_min) / co2_range +
            w_contrail * (p["contrail_ef"] - ef_min) / ef_range +
            w_time * (p["time_min"] - time_min) / time_range
        )
        if score < best_score:
            best_score = score
            best_idx = i

    return pareto_front[best_idx]
