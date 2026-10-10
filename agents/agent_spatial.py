# agents/agent_spatial.py
SPATIAL_DATA = [
    {'name': '港口与对外通道', 'type': '对外通道',
     'note': '客商进出与物资集散通道；1990年代初民用机场缺失属于基础设施短板'},
    {'name': '民用机场', 'type': '基础设施',
     'note': '当时福州没有民用机场，客商进不来、物资出不去，是建设重点'},
    {'name': '开发区与园区', 'type': '园区载体',
     'note': '“园区为基”的工业立市路径载体'},
    {'name': '元洪投资区', 'type': '园区',
     'note': '附件资料图示的对外投资区代表，与以侨引侨相关'},
    {'name': '苍霞片区', 'type': '城市更新',
     'note': '1983年棚户区，2017年改造为新城，体现拓新改旧'},
    {'name': '海上丝绸之路博览会', 'type': '开放交流空间',
     'note': '对外开放与经贸交流载体'},
    {'name': '侨商网络', 'type': '侨商网络',
     'note': '福州侨乡资源，是以侨引侨的空间纽带'},
]
def query_spatial(keyword=None, stype=None):
    result = [
        item for item in SPATIAL_DATA
        if (keyword is None or keyword in item['name'] or keyword in item['note'])
        and (stype is None or item['type'] == stype)
    ]
    return result if result else {'error': '知识库暂无匹配的空间要素'}
# 对接地图类API时，在返回结果中追加坐标字段即可，不改变接口形态
