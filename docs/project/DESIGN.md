# “3820”多智能体系统接口契约

本文件记录接口契约。可执行定义在 [contracts.py](../../contracts.py)，可运行示例在 [tests/fixtures/contracts.json](../../tests/fixtures/contracts.json)。改动契约时同步修改示例和测试。

## 配置边界

- [config.py](../../config.py) 集中读取项目根目录的 `.env` 与进程环境变量；进程环境变量优先。导入模块不读取密钥，也不连接模型。
- `ARK_API_KEY`、`LLM_MODEL` 用于在线模型调用，`EMBED_MODEL` 为旧版向量索引构建配置；缺失时服务仍能用本地规则和文本检索运行。当前聊天读取指南、`knowledge/library/` 中允许检索的 Markdown、`knowledge/data/public_sources/` 网页文本及 `knowledge/data/original_3820/` 扫描 OCR。PPT 和课程资料不进入聊天或资料检索；旧 PPT OCR 只作提取记录。`SERVICE_API_KEY` 设置后，`/chat` 与 `/library/*` 等受保护接口需要 `X-API-Key`；首页、静态资源、`/health` 和 `/favicon.ico` 可直接访问。可选 `SERVICE_CLIENTS_JSON` 定义多个客户端及 `chat`、`metrics`、`docs` 权限；`docs` 权限允许资料检索、预览和下载。调用时还需 `X-Client-ID`；客户端会话在 Checkpoint 中隔离。
- `ARK_BASE_URL`、`TOP_K`、`REQUEST_TIMEOUT`、`LOG_LEVEL` 已由调用方使用。`CHECKPOINT_PATH` 配置 SQLite 会话快照；`INDEX_PATH` 指向旧版向量索引。分类目录存在时忽略旧索引，防止检索到已排除资料。`MAX_BODY_BYTES` 和 `RATE_LIMIT_PER_MINUTE` 控制单实例入口。
- `get_settings()` 会缓存一次运行配置；修改环境变量后应重启服务。测试可直接调用 `load_settings(environ=..., dotenv_path=...)`，不读取本机密钥。

## 字段和状态

| 契约 | 必填字段 | 含义与约束 |
| --- | --- | --- |
| `SourceRef` | `source_file`、`data_version`、`verified` | `page_or_slide` 与 `section` 可为空；`verified=false` 不能作为已核验事实。 |
| `KnowledgeHit` | `chunk_id`、`content`、`source` | 分数和 `score_kind` 同时提供；`l2_distance` 越小越近，`similarity` 越大越近。 |
| `KnowledgeResult` | `status`、`hits` | `ok` 至少有一个片段；`insufficient_evidence` 表示无充分依据；`error` 需要 `ErrorInfo`。 |
| `SubTask` | `type`、`question` | `type` 仅为 `planning`、`indicator`、`spatial`、`evaluation`；指标任务还需 `key`，空间任务还需 `keyword`。指标任务的 `growth` 标记增长率计算，`target` 标记目标查询，均由原问题确定。 |
| `AgentResult` | `role`、`status` | `data` 是角色结果，`sources` 为实际用到的来源；`error` 状态必须给出错误码和说明。 |
| `ToolResult` | `status` | 三项只读工具统一返回 `data`、`sources` 和错误状态；未知工具名抛出校验错误。 |
| `ChatRequest` | `question` | 非空白、最多 4000 字符；`thread_id` 可选，最多 128 字符。 |
| `ChatResponse` | `request_id`、`status`、`answer`、`results` | `results` 中每项为 `AgentResult`；整体状态为 `ok`、`partial` 或 `error`。 |
| `ChatError` | `request_id`、`status`、`error` | `error` 包含机器可读的 `code` 和用户可读的 `message`。 |

`AgentResult.status=ok` 只表示角色执行成功，不表示所有事实已核验。前端必须查看 `sources[].verified`；来源为空时不能宣称已提供可追溯依据。`ErrorInfo.code` 使用小写字母、数字和下划线。当前 HTTP 层使用 `invalid_request`、`unauthorized`、`rate_limited`、`body_too_large`、`internal_error`；后续角色可以补充更细的错误码。

## 当前代码接入范围

- `knowledge/query_understanding.py` 在拆分前把常见同义说法、阶段问句笔误和当前 SQLite 会话的上一轮追问整理为独立问句。对规则未识别的简短提问，已配置的豆包模型只返回受限主题分类；分类结果仅用于选取已整理资料，不作为事实或引用。原始提问仍保存在会话快照中，不同客户端/会话不共享上一轮问题。
- `graph.py` 用 `SubTask` 校验主智能体拆分结果，非法任务不能进入工具层。
- `agents/answer_writer.py` 使用豆包 API 将角色结果组织成自然语言；生成文本必须保留关键数值与“待核对”“无法评估”等证据边界，模型失败或遗漏时退回自然语言模板。官方理论资料仅对理论分析类问题作为候选背景，实际使用的条目加入 `theory_context` 结果及来源；不得把新时代概念写成 1992 年规划的原始依据。来源与选用规则见 [理论资料](../理论资料.md)。
- 规划类问题先用本地知识库回答。若没有直接依据或最终答案仍明确表示无法定位，且问题属于“3820”或福州发展范围，`knowledge/model_fallback.py` 会调用已配置的豆包模型。回答正文直接给出内容，模型补充说明在下方小字展示；`results.model` 不附资料来源，不声称模型已经联网。指标冲突与目标达成判据不足保持原有证据边界；无关问题不调用模型补充。
- PPT 图片 OCR 的旧提取结果仍保存，但当前不进入检索。投资示意图问答优先引用扫描预览第 27 页，地图主要名称经图像人工转录存于 `knowledge/map_labels.json`。
- `knowledge/library_search.py` 只根据清单中允许公开的 ID 定位文件；课程和 PPT 即使知道路径，也无法经 `/library/*` 预览或下载。
- `app.py` 用 `ChatRequest`、`ChatResponse` 和 `ChatError` 校验 HTTP 边界；旧角色结果经适配后放入 `AgentResult.data`，不会凭空生成来源。
- `/metrics` 展示单进程内的请求、延迟、HTTP 错误、超时及检索质量比率；节点日志只保留请求/会话标识、角色、节点、耗时和异常类型，避免输出问题正文与密钥。生产环境需要独立监控和集中日志。
- `knowledge/knowledge_base.py` 的 `search` 返回 `KnowledgeResult` 和 `KnowledgeHit`；`graph.py` 把角色输出转为 `AgentResult`，来源保持 `verified=false`。
- 向量检索在距离接近首位时保留一条原件扫描 OCR 命中，同时返回未经修改的原始距离；OCR 页码为平台预览页码。带指标的目标问题进入确定性目标查询，区分原表 GNP 列值与指南公式推算的 GDP 目标；其他目标问题进入规划检索，不能把指南中的完成值当作原始目标值。
- 原始资料尚未核验时，示例夹具中的来源均为 `verified=false`。本地夹具只验证接口，不充当历史事实的独立证明。

## 离线验证

运行 `python -m pytest -m offline -q`。普通测试不调用外部服务。在线模型与向量索引已在本机演示环境做过手动 smoke test；记录见 [验收记录](../验收记录.md)，不纳入普通 CI。
