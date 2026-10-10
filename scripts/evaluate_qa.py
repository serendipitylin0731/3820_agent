"""逐题记录在线演示答案、来源与可机械核对的期望；人工复核另行记录。"""

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from app import app
from config import get_settings


CASES = Path('tests/fixtures/qa_cases.json')
REPORT = Path('var/qa_report.json')


def evaluate_case(client, case, headers):
    response = client.post('/chat', headers=headers,
                           json={'question': case['question'],
                                 'thread_id': f'qa-{uuid.uuid4().hex}'})
    body = response.json()
    answer = body.get('answer', '')
    results = body.get('results', {})
    matched = [(role, item) for role, item in results.items()
               if role == case['expected_role'] or role.startswith(case['expected_role'] + '_')]
    sources = [source for item in results.values() for source in item.get('sources', [])]
    source_text = json.dumps(sources, ensure_ascii=False)
    checks = {
        'http_200': response.status_code == 200,
        'app_ok': body.get('status') == 'ok',
        'role_status': any(item.get('status') == case['expected_role_status'] for _, item in matched),
        'answer_terms': all(term in answer for term in case['answer_contains']),
        'source_terms': all(term in source_text for term in case['source_contains']),
        'has_source_when_ok': bool(sources) if case['expected_role_status'] == 'ok' else True,
    }
    return {'id': case['id'], 'question': case['question'], 'expected': {
        key: value for key, value in case.items() if key not in ('id', 'question')},
        'actual': {'http_status': response.status_code, 'app_status': body.get('status'),
                   'answer': answer, 'role_statuses': {role: item.get('status') for role, item in results.items()},
                   'sources': sources},
        'checks': checks, 'mechanical_pass': all(checks.values()), 'manual_review': 'pending'}


def main():
    logging.disable(logging.CRITICAL)
    settings = get_settings()
    headers = {'X-API-Key': settings.service_api_key.get_secret_value()} if settings.service_api_key else {}
    cases = json.loads(CASES.read_text(encoding='utf-8'))
    with TestClient(app) as client:
        rows = [evaluate_case(client, case, headers) for case in cases]
    report = {'ran_at_utc': datetime.now(timezone.utc).isoformat(),
              'count': len(rows), 'mechanical_passed': sum(row['mechanical_pass'] for row in rows),
              'cases': rows}
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'count': report['count'], 'mechanical_passed': report['mechanical_passed'],
                      'failed_ids': [row['id'] for row in rows if not row['mechanical_pass']],
                      'report': str(REPORT)}, ensure_ascii=False))
    if report['mechanical_passed'] != report['count']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
