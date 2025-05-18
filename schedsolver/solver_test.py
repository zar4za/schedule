import pytest
from solver import solve_schedule

# Helper to create a basic request for one staff and one shift

def make_simple_request():
    return {
        "request_id": "test1",
        "staff": [
            {"id": 1, "name": "Dr. A", "tg_id": 100, "max_week_hours": 40.0, "preferences": []}
        ],
        "shifts": [
            {"shift_id": "s1", "start": "2025-06-01T08:00:00Z", "end": "2025-06-01T16:00:00Z", "required_count": 1, "is_night": False}
        ],
        "unavailability": [],
        "previous_assignments": []
    }


def test_simple_assignment():
    """
    A single available staff should be assigned to the only shift.
    """
    req = make_simple_request()
    res = solve_schedule(req)
    assert res["status"] == "success"
    assert len(res["assignments"]) == 1
    assert res["assignments"][0]["shift_id"] == "s1"
    assert res["assignments"][0]["staff_id"] == 1


def test_unavailability_block():
    """
    If the only staff is unavailable, the solver cannot assign and should return non-success.
    """
    req = make_simple_request()
    req["unavailability"] = [
        {"staff_id": 1, "from": "2025-06-01T00:00:00Z", "to": "2025-06-02T00:00:00Z", "timestamp": "2025-05-18T00:00:00Z"}
    ]
    res = solve_schedule(req)
    assert res["status"] != "success"


def test_rest_violation():
    """
    A single staff cannot cover two shifts less than 11 hours apart, so expect failure.
    """
    req = {
        "request_id": "test2",
        "staff": [
            {"id": 1, "name": "Dr. B", "tg_id": 101, "max_week_hours": 40.0, "preferences": []}
        ],
        "shifts": [
            {"shift_id": "s1", "start": "2025-06-01T08:00:00Z", "end": "2025-06-01T16:00:00Z", "required_count": 1, "is_night": False},
            {"shift_id": "s2", "start": "2025-06-01T20:00:00Z", "end": "2025-06-02T06:00:00Z", "required_count": 1, "is_night": True}
        ],
        "unavailability": [],
        "previous_assignments": []
    }
    res = solve_schedule(req)
    # Should not assign both shifts to the same staff; thus status != success
    assert res["status"] != "success"

if __name__ == "__main__":
    pytest.main()
