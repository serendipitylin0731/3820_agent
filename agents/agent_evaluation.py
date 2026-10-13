"""目标达成率与可比性判断；定性目标没有外部基准时拒绝自动评估。"""
import json
import math
from pathlib import Path


def _nonnegative_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0


def compute_achievement(actual, target, direction='up'):
    """上升型：实际/目标；下降型：达标封顶 100%，超出上限为目标/实际。"""
    if not _nonnegative_number(actual) or not _nonnegative_number(target):
        return None
    if direction == 'up':
        if target == 0:
            return None
        ratio = actual / target
    elif direction == 'down':
        ratio = 1.0 if actual <= target else target / actual
    else:
        return None
    return round(ratio * 100, 1)


def evaluate_goal(actual=None, target=None, *, direction='up',
                  actual_basis=None, target_basis=None, interval=None,
                  benchmark=None, rule=None):
    """返回可解释状态；区间型和定性型只有显式判据才能判定。"""
    if actual_basis and target_basis and actual_basis != target_basis:
        return {'status':'无法评估', 'reason':'实际值与目标值统计口径不同'}
    if direction in ('up', 'down'):
        rate = compute_achievement(actual, target, direction)
        if rate is None:
            return {'status':'无法评估', 'reason':'实际值、目标值或分母无效'}
        return {'status':'已评估', 'achievement_percent':rate,
                'conclusion':'达标' if rate >= 100 else '未达标',
                'formula':'实际值/目标值×100%' if direction == 'up' else '不高于上限记为100%；超出上限按上限/实际值×100%'}
    if direction == 'range':
        if not interval or len(interval) != 2 or not _nonnegative_number(actual) or any(not _nonnegative_number(x) for x in interval) or interval[0] > interval[1]:
            return {'status':'无法评估', 'reason':'缺少有效区间和实际值'}
        return {'status':'已评估', 'achievement_percent':None,
                'conclusion':'达标' if interval[0] <= actual <= interval[1] else '未达标',
                'formula':'实际值落在目标区间内判为达标'}
    if direction == 'qualitative':
        if not benchmark or not rule:
            return {'status':'无法评估', 'reason':'缺少比较对象、年份、口径或判据'}
        return {'status':'待人工核验', 'reason':'定性目标需按明确判据与外部基准核验'}
    return {'status':'无法评估', 'reason':'目标方向无效'}


def eval_1995_phase(data):
    rows = []
    original = json.loads((Path(__file__).parents[1] / 'knowledge' / 'original_targets.json').read_text(encoding='utf-8'))
    for key in ('gnp', 'gdp', 'gdp_per_capita', 'urban_income', 'rural_income', 'industry_output'):
        info = data[key]
        base = info['values'][1990]
        actual = info['values'][1995]
        target = original['gnp']['1995'] if key == 'gnp' else round(base * 2, 2)
        basis = '原始规划目标表列值' if key == 'gnp' else '指南表4阶段目标算法（1990年基数翻番）'
        rows.append({'指标':info['name'], '单位':info['unit'],
                     '基准':base, '目标':target, '实际':actual,
                     '达成率':compute_achievement(actual, target),
                     '公式':'1995实际值/所列目标值×100%',
                     '目标依据':basis, '来源':info['source_ref'],
                     '目标来源':original['source_ref'] if key == 'gnp' else info['source_ref']})
    return rows
