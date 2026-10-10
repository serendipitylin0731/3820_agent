"""可选择引用的官方理论资料；均作为后来的解读视角，不作为 1992 年史料。"""

THEORY_CONTEXT = {
    'marxist_method': {
        'text': '马克思主义的方法强调实事求是、从实际出发，运用实践和调查研究认识与解决具体问题。这里可用于分析“3820”规划的方法，但不能说 1992 年文本明确使用了后来形成的理论表述。',
        'source': {
            'source_file': 'https://dl.mof.gov.cn/lianzhengjianshe/202007/t20200713_3548431.htm',
            'section': '实事求是与马克思主义立场观点方法',
            'page_or_slide': None,
            'data_version': '财政部网页，2020-07',
            'verified': True,
        },
    },
    'new_era_method': {
        'text': '习近平新时代中国特色社会主义思想的世界观和方法论概括为“六个必须坚持”，其中人民至上、问题导向、系统观念可用于当代视角下分析长期规划。该概括属于新时代，不能写成 1992 年规划的原始理论依据。',
        'source': {
            'source_file': 'https://he.mof.gov.cn/zt4/dj/xxyd/202304/t20230427_3881653.htm',
            'section': '“六个必须坚持”的世界观和方法论',
            'page_or_slide': None,
            'data_version': '财政部转载《求是》，2023-04',
            'verified': True,
        },
    },
    'new_development': {
        'text': '创新、协调、绿色、开放、共享的新发展理念是党的十八届五中全会提出的新时代发展理念。若用于理解“3820”工程的当代意义，必须标明是后来的理论参照。',
        'source': {
            'source_file': 'https://www.ndrc.gov.cn/xwdt/ztzl/NEW_srxxgcjjpjjsx/jjsxyjqk/tgyg/202301/t20230117_1363350_ext.html',
            'section': '完整、准确、全面贯彻新发展理念',
            'page_or_slide': None,
            'data_version': '国家发展改革委网页，2023-01',
            'verified': True,
        },
    },
}


def select_theory(question: str, results: dict) -> dict:
    """仅在问题需要理论分析且已有 3820 来源时提供候选背景。"""
    if not any(item.get('status') == 'ok' and item.get('sources') for item in results.values()):
        return {}
    explicit = ('理论', '思想', '马克思', '方法论', '哲学', '人民至上', '新发展理念',
                '当代意义', '时代意义', '启示', '问题导向', '系统观念')
    if not any(word in question for word in explicit):
        return {}
    selected = {}
    if '马克思' in question or '哲学' in question or '实事求是' in question:
        selected['marxist_method'] = THEORY_CONTEXT['marxist_method']
    if any(word in question for word in ('习近平新时代', '人民至上', '问题导向', '系统观念', '启示', '当代意义', '时代意义')):
        selected['new_era_method'] = THEORY_CONTEXT['new_era_method']
    if '新发展理念' in question or '高质量发展' in question:
        selected['new_development'] = THEORY_CONTEXT['new_development']
    if not selected:
        selected['new_era_method'] = THEORY_CONTEXT['new_era_method']
    return dict(list(selected.items())[:2])
