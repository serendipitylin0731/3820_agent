"""空间要素查询；没有可信坐标时不返回坐标。"""
from knowledge.domain import spatial_features


def query_spatial(keyword=None, stype=None, period=None):
    items = [item for item in spatial_features()
             if (not keyword or keyword in item['name'] or keyword in item['note'] or keyword in item.get('path', ''))
             and (not stype or item['type'] == stype)
             and (not period or item.get('period') == period)]
    return items if items else {'error': '知识库暂无匹配的空间要素'}
