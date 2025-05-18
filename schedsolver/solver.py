from ortools.sat.python import cp_model


def generate_shift_schedule(doctors, days, shifts,
                            requirements,
                            availability,
                            shift_durations,
                            max_weekly_hours,
                            min_rest_hours=11,
                            preferences=None,
                            alpha=1000,
                            beta=5,
                            gamma=1):
    """
    Generates an optimized weekly shift schedule based on the mathematical model (Formulas 8.1–8.6).

    Args:
        doctors: List of doctor IDs (|I|).
        days: List of day indices (|J|).
        shifts: List of shift IDs (|K|).
        requirements: Dict (day, shift) -> required number of doctors r_{jk}.
        availability: Dict (doc, day, shift) -> binary a_{ijk} availability.
        shift_durations: Dict shift -> duration t_k (hours).
        max_weekly_hours: Dict doc -> max hours h_i^max.
        min_rest_hours: Minimum rest between any two shifts (hours).
        preferences: Optional dict (doc, day, shift) -> preference weight p_{ijk}.
        alpha: Penalty weight for undercoverage (>=1000).
        beta: Weight for workload fairness term (1–10).
        gamma: Weight for preference term (1–5).

    Returns:
        schedule: Dict (doc, day, shift) -> 0/1 assignment x_{ijk}.
    """
    model = cp_model.CpModel()

    # Precompute total required hours H_sum = sum_{j,k} r_{jk} * t_k
    H_sum = sum(requirements[(j, k)] * shift_durations[k] for j in days for k in shifts)
    # Average hours per doctor (integer division)
    H_avg = H_sum // len(doctors)

    # Variables
    x = {}   # assignment x_{i,j,k}
    for i in doctors:
        for j in days:
            for k in shifts:
                x[(i, j, k)] = model.NewBoolVar(f'x_{i}_{j}_{k}')

    u = {}   # undercoverage u_{j,k}
    for j in days:
        for k in shifts:
            max_u = requirements.get((j, k), len(doctors))
            u[(j, k)] = model.NewIntVar(0, max_u, f'u_{j}_{k}')

    h = {}   # total hours h_i
    d = {}   # deviation from average d_i
    for i in doctors:
        h[i] = model.NewIntVar(0, max_weekly_hours[i], f'h_{i}')
        # Domain of d_i must cover max deviation |h_i - H_avg|, up to H_avg
        d[i] = model.NewIntVar(0, H_avg, f'd_{i}')

    # Constraints
    # (8.2) Coverage: sum_i x_{i,j,k} + u_{j,k} >= r_{jk}
    for j in days:
        for k in shifts:
            req = requirements[(j, k)]
            model.Add(sum(x[(i, j, k)] for i in doctors) + u[(j, k)] >= req)

    # (8.3) Availability: x_{i,j,k} <= a_{i,j,k}
    for i in doctors:
        for j in days:
            for k in shifts:
                if availability.get((i, j, k), 0) == 0:
                    model.Add(x[(i, j, k)] == 0)

    # (8.4) Weekly hours: h_i = sum_{j,k} t_k * x_{i,j,k}  and <= max
    for i in doctors:
        model.Add(h[i] == sum(shift_durations[k] * x[(i, j, k)] for j in days for k in shifts))
        model.Add(h[i] <= max_weekly_hours[i])

    # (8.5a) Rest constraints: simplified example
    if 'evening' in shifts and 'morning' in shifts:
        for i in doctors:
            for j in days[:-1]:
                model.Add(x[(i, j, 'evening')] + x[(i, j+1, 'morning')] <= 1)

    # (8.5b) Load deviation linearization
    for i in doctors:
        model.Add(h[i] - H_avg <= d[i])
        model.Add(H_avg - h[i] <= d[i])

    # Objective (8.6): alpha * sum u + beta * sum d - gamma * sum p*x
    obj_terms = [alpha * u[(j, k)] for j in days for k in shifts] + [beta * d[i] for i in doctors]
    if preferences:
        for i in doctors:
            for j in days:
                for k in shifts:
                    w = preferences.get((i, j, k), 0)
                    if w:
                        obj_terms.append(-gamma * w * x[(i, j, k)])

    model.Minimize(sum(obj_terms))

    # Solve with diagnostic logs on infeasibility
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 60
    solver.parameters.num_search_workers = 8
    solver.parameters.log_search_progress = True

    status = solver.Solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        print('Solver status:', solver.StatusName(status))
        raise ValueError('No feasible solution found! Consider relaxing constraints or checking input data.')

    # Extract schedule
    schedule = {(i, j, k): int(solver.Value(x[(i, j, k)])) for i in doctors for j in days for k in shifts}
    return schedule


if __name__ == '__main__':
    # Example usage
    doctors = ['Dr_A', 'Dr_B', 'Dr_C']
    days = list(range(7))
    shifts = ['morning', 'day', 'evening']
    requirements = {(j, k): 2 for j in days for k in shifts}
    availability = {(i, j, k): 1 for i in doctors for j in days for k in shifts}
    shift_durations = {'morning': 8, 'day': 8, 'evening': 8}
    max_weekly_hours = {i: 40 for i in doctors}
    preferences = {(i, j, k): 1 for i in doctors for j in days for k in shifts}

    schedule = generate_shift_schedule(
        doctors, days, shifts,
        requirements,
        availability,
        shift_durations,
        max_weekly_hours,
        min_rest_hours=11,
        preferences=preferences,
        alpha=1000,
        beta=5,
        gamma=1
    )
    for j in days:
        print(f"Day {j}:")
        for k in shifts:
            print(f"  {k}: {[i for i in doctors if schedule[(i, j, k)]]}")
