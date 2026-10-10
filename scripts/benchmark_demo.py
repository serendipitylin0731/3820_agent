"""对本机 ASGI 服务做有限的演示压测；不输出答案或密钥。"""

import asyncio
import json
import time
import uuid
from pathlib import Path

import httpx

from app import app
from config import get_settings


QUESTIONS = [
    '3820战略工程的三个阶段目标是什么？',
    '1995年福州GDP目标完成情况如何？',
    '福州经济技术开发区在战略中的作用是什么？',
    '2010年GDP是多少？',
    '3820战略工程对城市空间布局有什么安排？',
]


async def main():
    settings = get_settings()
    headers = {}
    if settings.service_api_key:
        headers['X-API-Key'] = settings.service_api_key.get_secret_value()
    transport = httpx.ASGITransport(app=app)
    semaphore = asyncio.Semaphore(2)
    async with httpx.AsyncClient(transport=transport, base_url='http://demo.local', timeout=90) as client:
        async def ask_one(index, question):
            async with semaphore:
                started = time.perf_counter()
                try:
                    response = await client.post('/chat', headers=headers,
                                                 json={'question': question,
                                                       'thread_id': f'benchmark-{uuid.uuid4().hex}'})
                    payload = response.json()
                    return {'index': index, 'http_status': response.status_code,
                            'app_status': payload.get('status'),
                            'duration_s': round(time.perf_counter() - started, 3)}
                except Exception as exc:
                    return {'index': index, 'http_status': None, 'app_status': 'transport_error',
                            'duration_s': round(time.perf_counter() - started, 3),
                            'error_type': type(exc).__name__}

        results = await asyncio.gather(*(ask_one(i, question) for i, question in enumerate(QUESTIONS * 2)))
    durations = sorted(item['duration_s'] for item in results)
    p95 = durations[min(len(durations) - 1, int(len(durations) * .95))]
    failures = sum(item['http_status'] is None or item['http_status'] >= 500 for item in results)
    business_failures = sum(item['app_status'] != 'ok' for item in results)
    report = {'concurrency': 2, 'requests': len(results), 'p95_s': p95,
              'http_5xx_or_transport_error_rate': failures / len(results),
              'business_failure_rate': business_failures / len(results),
              'target_p95_s': 12, 'target_error_rate': 0,
              'passed': p95 <= 12 and failures == 0 and business_failures == 0,
              'results': results}
    path = Path('var/benchmark_report.json')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({key: value for key, value in report.items() if key != 'results'}, ensure_ascii=False))


if __name__ == '__main__':
    asyncio.run(main())
