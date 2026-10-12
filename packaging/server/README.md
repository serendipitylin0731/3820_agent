# 3820 网页版服务器部署包

此目录已包含网页服务代码、运行时文档、可读取的资料文字及原文件、现有向量索引。它不含 API Key、Python 虚拟环境、Windows 安装包和未转写的视频。请将**整个目录**上传服务器，保持目录结构不变。

## Linux 直接运行

服务器安装 Python 3.11 后，进入此目录：

```bash
python3.11 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
cp .env.example .env
```

编辑 `.env`，填写服务器使用的 `ARK_API_KEY` 和已开通的 `LLM_MODEL`。包内索引使用 `doubao-embedding-vision-251215`；如需启用它，填写 `EMBED_MODEL=doubao-embedding-vision-251215`，并设置 `VECTOR_MAX_DISTANCE=1.2`。如果改用其他向量模型或增删资料，先运行 `.venv/bin/python -m knowledge.knowledge_base` 重建索引并重新校准距离阈值。建议为公开访问设置 `SERVICE_API_KEY`，它是网站访问密码，与豆包 API Key 不同。

启动服务：

```bash
mkdir -p var
.venv/bin/python -m uvicorn app:app --host 0.0.0.0 --port 8000
```

在服务器上执行 `curl http://127.0.0.1:8000/health`，应得到 `{"status":"ok"}`。随后用浏览器访问 `http://服务器IP:8000/`。需要长期运行时，将上述启动命令放进 systemd 或现有进程管理器，并用 Nginx/Caddy 配置 HTTPS 反向代理。

## Docker 运行

在此目录创建 `.env` 后执行：

```bash
docker build -t 3820-agent-web .
docker run -d --name 3820-agent-web --restart unless-stopped \
  --env-file .env -p 8000:8000 -v "$(pwd)/var:/app/var" 3820-agent-web
```

Docker 镜像包含本目录中的可检索资料；`var/` 挂载用于保存会话快照和索引。`.env` 被排除在镜像之外，由 `--env-file` 在启动时提供。资料更新后重新生成部署包、重建镜像，并按需重建向量索引。

## 包内文件

`app.py`、`graph.py` 等根目录模块，`agents/`、`knowledge/`、`web/`、`desktop_app/runtime.py`、两份运行时 Markdown 文档、`requirements.lock` 和 `.env.example` 是服务所需内容。`knowledge/data/` 包含已收录的 Word/PPT、公开网页 TXT、扫描 OCR TXT、PPT 图片 OCR 和各自清单；`var/knowledge_index/` 包含当前资料的向量索引。其他本地文件无需上传。
