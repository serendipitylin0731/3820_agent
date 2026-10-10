import math
from agents.agent_evaluation import compute_achievement, evaluate_goal


def test_invalid_and_downward_targets():
    assert compute_achievement(0, 0) is None
    assert compute_achievement(-1, 2) is None
    assert compute_achievement(math.nan, 2) is None
    assert compute_achievement(0, 0, 'down') == 100.0
    assert compute_achievement(120, 100, 'down') == 83.3


def test_incomparable_interval_and_qualitative_goals():
    assert evaluate_goal(10, 20, actual_basis='a', target_basis='b')['status'] == '无法评估'
    assert evaluate_goal(5, direction='range', interval=(4, 6))['conclusion'] == '达标'
    assert evaluate_goal(7, direction='range', interval=(4, 6))['conclusion'] == '未达标'
    assert evaluate_goal(direction='qualitative')['status'] == '无法评估'
