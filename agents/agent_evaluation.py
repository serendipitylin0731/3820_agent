# agents/agent_evaluation.py
def compute_achievement(actual, target, direction='up'):
    # down表示目标为上限：实际值不高于目标即视为达标（100%）
    if actual is None or target is None or direction not in ('up', 'down'):
        return None
    if direction == 'up':
        if target <= 0:
            return None
        ratio = actual / target
    else:
        if actual < 0 or target < 0:
            return None
        ratio = 1.0 if actual <= target else (target / actual if actual else 1.0)
    return round(ratio * 100, 1)
def eval_1995_phase(data):
    # 以附件数据核算：3年目标=1990年指标*2，计算1995年达成率
    rows = []
    for key in ('gnp', 'gdp', 'gdp_per_capita', 'urban_income', 'rural_income', 'industry_output'):
        info = data[key]
        base = info['values'][1990]
        actual = info['values'][1995]
        target = round(base * 2, 2)
        rows.append({
            '指标': info['name'], '单位': info['unit'],
            '基准': base, '目标': target, '实际': actual,
            '达成率': compute_achievement(actual, target),
        })
    return rows
