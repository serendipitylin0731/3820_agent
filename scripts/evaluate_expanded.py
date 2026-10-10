"""对页面示例与扩展问题做在线广覆盖评测；完整结果仅写入 Git 忽略的 var/。"""

import json
import logging
import re
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from app import app
from config import get_settings


EXTRA = [
    ('airport_original', '长乐国际机场建设如何服务于3820工程的对外开放目标？'),
    ('airport_runway_model', '福州长乐国际机场二期扩建工程主跑道何时贯通？'),
    ('airport_ambiguity', '福州长乐国际机场二期扩建工程东跑道何时贯通？'),
    ('airport_1997', '长乐国际机场在哪一年正式通航？它与3820工程有什么关系？'),
    ('seaport', '福州港口建设怎样服务于3820工程的对外开放？'),
    ('yuanhong', '元洪投资区在3820工程中承担什么作用？'),
    ('mawei', '福州经济技术开发区在闽江口战略布局中是什么位置？'),
    ('old_city', '3820工程为什么以福州老市区为依托？'),
    ('coastal_wings', '沿海县市区作为南北两翼具体指什么？'),
    ('mountain_counties', '山区县在3820工程空间布局中扮演什么角色？'),
    ('overseas_chinese', '3820工程如何利用侨资侨力推进开放？'),
    ('marine', '海上福州提出哪些海洋经济建设方向？'),
    ('modern_city', '3820工程为什么提出建设现代化国际城市？'),
    ('background_1992', '1992年福州制定3820工程时面临哪些发展问题？'),
    ('research', '3820工程的编制进行了哪些调查研究？'),
    ('planning_process', '3820工程是怎样形成并得到论证的？'),
    ('growth_1995', '1995年福州GDP与1990年相比增长了百分之几？'),
    ('gdp_2010', '2010年福州GDP有哪些不同版本？'),
    ('gnp_target', '1995年福州GNP原始目标是多少？'),
    ('income_rural', '1995年福州农村居民人均纯收入是多少？'),
    ('industry_share', '2010年福州三次产业结构如何？'),
    ('target_2010', '3820工程到2010年的远期目标是什么？'),
    ('target_2000', '3820工程到2000年的中期目标是什么？'),
    ('assessment_2010', '能否仅凭现有资料判定3820工程2010年目标已经达成？'),
    ('theory_new_era', '从新时代发展理念看3820工程有什么启示？'),
    ('model_fuzhou_development', '福州长乐国际机场二期扩建如何支撑城市发展？'),
    ('unrelated_chip', '量子芯片的制程是多少？'),
    ('unrelated_weather', '福州明天天气如何？'),
    ('imaginary', '3820工程发射的宇宙飞船叫什么？'),
]


def cases():
    script = Path('web/app.js').read_text(encoding='utf-8')
    examples = re.findall(r"\{ category: '([^']+)', label: '[^']+', question: '([^']+)' \}", script)
    return [(f'ui_{i:02d}', question) for i, (_, question) in enumerate(examples, 1)] + EXTRA


def evaluate(item):
    case_id, question = item
    settings = get_settings()
    headers = {'X-API-Key': settings.service_api_key.get_secret_value()} if settings.service_api_key else {}
    with TestClient(app) as client:
        response = client.post('/chat', headers=headers,
                               json={'question': question, 'thread_id': f'expanded-{uuid.uuid4().hex}'})
    body = response.json()
    results = body.get('results', {})
    sources = [source for result in results.values() for source in result.get('sources', [])]
    answer = body.get('answer', '')
    checks = {'http_ok': response.status_code == 200,
              'app_ok': body.get('status') == 'ok'}
    if case_id == 'airport_original':
        checks['original_page'] = bool(sources) and '预览第255页' in str(sources[0].get('page_or_slide'))
        checks['local_answer'] = 'model' not in results
    elif case_id == 'airport_1997':
        checks['actual_opening_year'] = '1997' in answer and '计划1996' not in answer
    elif case_id == 'industry_share':
        checks['three_shares'] = all(term in answer for term in ('9.05', '44.88', '46.06'))
    elif case_id in {'ui_13', 'research'}:
        checks['local_source'] = bool(sources) and 'model' not in results
    elif case_id == 'airport_runway_model':
        checks['model_supplement'] = 'model' in results and '豆包模型' in answer
    elif case_id in {'unrelated_chip', 'unrelated_weather'}:
        checks['no_model_supplement'] = 'model' not in results
    elif case_id == 'ui_05':
        checks['no_spurious_achievement'] = '226.6' not in answer
    elif case_id == 'ui_06':
        checks['growth_not_achievement'] = '353.3' in answer and '226.6' not in answer
    return {'id': case_id, 'question': question, 'http_status': response.status_code,
            'status': body.get('status'), 'answer': answer, 'checks': checks,
            'roles': {role: item.get('status') for role, item in results.items()},
            'sources': sources,
            'unlocated': any(term in answer for term in
                             ('依据不足', '无法明确', '未查找到', '未找到', '无法核实', '无法评估'))
                         and 'model' not in results}


def main():
    logging.disable(logging.CRITICAL)
    items = cases()
    rows = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = {pool.submit(evaluate, item): item[0] for item in items}
        for future in as_completed(futures):
            case_id = futures[future]
            try:
                row = future.result()
            except Exception as exc:
                row = {'id': case_id, 'error_type': type(exc).__name__}
            rows.append(row)
            print(f"{len(rows)}/{len(items)} {case_id}: {row.get('status', row.get('error_type'))} "
                  f"model={'model' in row.get('roles', {})} unlocated={row.get('unlocated')}", flush=True)
    rows.sort(key=lambda row: next(i for i, item in enumerate(items) if item[0] == row['id']))
    report = {'ran_at_utc': datetime.now(timezone.utc).isoformat(), 'count': len(rows), 'cases': rows}
    path = Path('var/qa_expanded_report.json')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    failed = [row['id'] for row in rows if not all(row.get('checks', {}).values())]
    print(json.dumps({'count': len(rows), 'failed': failed,
                      'unlocated': [row['id'] for row in rows if row.get('unlocated')],
                      'report': str(path)}, ensure_ascii=False))
    if failed:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
