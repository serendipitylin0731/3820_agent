# “3820”多智能体系统接口契约

本文件记录接口契约。可执行定义在 [contracts.py](contracts.py)，可运行示例在 [tests/fixtures/contracts.json](tests/fixtures/contracts.json)。改动契约时同步修改示例和测试。

## 配置边界

- [config.py](config.py) 集中读取项目根目录的 `.env` 与进程环境变量；进程环境变量优先。导入模块不读取密钥，也不连接模型。
- `ARK_API_KEY`、`LLM_MODEL`、`EMBED_MODEL` 是在线问答服务启动所需配置；缺失时启动失败并列出缺少的变量名，不显示密钥值。`PPT_PATH` 是当前 PPT 检索器的输入路径，仅在检索时检查；指标等纯数据能力不依赖该文件。
- `ARK_BASE_URL`、`TOP_K`、`REQUEST_TIMEOUT`、`LOG_LEVEL` 已由调用方使用。`CHECKPOINT_PATH` 已集中声明，持久化 Checkpoint 的实际接入属于 M5。当前的 `.env.example` 中 `PPT_PATH` 只是指南示例文件名，正式资料可采用其他来源；非 PPT 格式的解析器属于 M2。
- `get_settings()` 会缓存一次运行配置；修改环境变量后应重启服务。测试可直接调用 `load_settings(environ=..., dotenv_path=...)`，不读取本机密钥。

## 字段和状态

| 契约 | 必填字段 | 含义与约束 |
| --- | --- | --- |
| `SourceRef` | `source_file`、`data_version`、`verified` | `page_or_slide` 与 `section` 可为空；`verified=false` 不能作为已核验事实。 |
| `KnowledgeHit` | `chunk_id`、`content`、`source` | 分数和 `score_kind` 同时提供；`l2_distance` 越小越近，`similarity` 越大越近。 |
| `KnowledgeResult` | `status`、`hits` | `ok` 至少有一个片段；`insufficient_evidence` 表示无充分依据；`error` 需要 `ErrorInfo`。 |
| `SubTask` | `type`、`question` | `type` 仅为 `planning`、`indicator`、`spatial`、`evaluation`；指标任务还需 `key`，空间任务还需 `keyword`。 |
| `AgentResult` | `role`、`status` | `data` 是角色结果，`sources` 为实际用到的来源；`error` 状态必须给出错误码和说明。 |
| `ChatRequest` | `question` | 非空白、最多 4000 字符；`thread_id` 可选，最多 128 字符。 |
| `ChatResponse` | `request_id`、`status`、`answer`、`results` | `results` 中每项为 `AgentResult`；整体状态为 `ok`、`partial` 或 `error`。 |
| `ChatError` | `request_id`、`status`、`error` | `error` 包含机器可读的 `code` 和用户可读的 `message`。 |

`AgentResult.status=ok` 只表示角色执行成功，不表示所有事实已核验。前端必须查看 `sources[].verified`；来源为空时不能宣称已提供可追溯依据。`ErrorInfo.code` 使用小写字母、数字和下划线。当前 HTTP 层使用 `invalid_request`、`agent_error`、`internal_error`；后续角色可以补充更细的错误码。

## 当前代码接入范围

- `graph.py` 用 `SubTask` 校验主智能体拆分结果，非法任务不能进入工具层。
- `app.py` 用 `ChatRequest`、`ChatResponse` 和 `ChatError` 校验 HTTP 边界；旧角色结果经适配后放入 `AgentResult.data`，不会凭空生成来源。
- `knowledge/knowledge_base.py` 目前仍返回字符串或元组；B 在 M2 中将检索输出适配为 `KnowledgeResult` 和 `KnowledgeHit`。C 在 M4 中逐步让角色直接返回 `AgentResult`。
- 原始资料尚未核验时，示例夹具中的来源均为 `verified=false`。本地夹具只验证接口，不充当历史事实的独立证明。

## 离线验证

运行 `python -m pytest -m offline -q`。普通测试也不调用外部服务；需要真实密钥和资料的用例将来使用 `online` 标记，单独运行。

