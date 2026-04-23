# 昇腾 310 智能助手（非 Gradio）

这是一个真正可产品化的 Agent 原型：

- **后端**：FastAPI（REST API）
- **前端**：原生 HTML/CSS/JS（侧边栏会话 + 参数面板 + 证据区）
- **Agent 编排**：MoFix 风格四阶段 `规划 -> 检索 -> 生成 -> 审校`
- **知识源**：`data/knowledge.json`（MindIE + vLLM 310P POC）

## 1) 本地运行

```bash
cd /path/to/310
chmod +x run.sh
./run.sh
```

访问：`http://127.0.0.1:7860`

## 2) 环境变量（自然语言增强）

可选配置，配置后回答会从“本地证据模板”升级为“自然语言生成”：

- `OPENAI_API_KEY`
- `OPENAI_BASE_URL`（OpenAI 兼容接口，如 `https://api.openai.com/v1`）
- `OPENAI_MODEL`（如 `gpt-4o-mini`）

支持项目根目录 `.env` 自动加载（无需每次命令行手工传参）：

```bash
cp .env.example .env
# 然后编辑 .env 填入你的真实密钥
```

服务端基础变量：

- `HOST`（默认 `0.0.0.0`）
- `PORT`（默认 `7860`）

## 3) API

### 健康检查

`GET /api/health`

### 对话接口

`POST /api/chat`

示例：

```json
{
  "message": "帮我对比 MindIE 和 vLLM 310P 的部署差异",
  "history": [{"role": "user", "content": "前一轮问题"}],
  "top_k": 8,
  "temperature": 0.2,
  "mode": "balanced",
  "enable_remote": true
}
```

返回：答案、意图、计划步骤、证据列表、审校结果等结构化字段。

## 4) Docker

```bash
docker build -t ascend310-agent .
docker run --rm -p 7860:7860 ascend310-agent
```

## 5) Hugging Face Spaces 部署（推荐）

推荐 **Hugging Face Spaces（Docker SDK）**，因为本项目已经包含 `Dockerfile`，可直接构建并得到固定访问链接。

### 5.1 准备代码仓库

将以下内容推送到你的 GitHub 仓库（或直接上传到 Space 仓库）：

- `Dockerfile`
- `requirements.txt`
- `app.py`
- `src/`
- `web/`
- `data/`
- `.dockerignore`

> 注意：不要提交 `.env`，密钥应放在 Space Secrets。

### 5.2 创建 Space

1. 打开 Hugging Face，点击 **New Space**。
2. 选择 **SDK = Docker**。
3. 选择公开或私有。
4. 关联你的 GitHub 仓库（或创建后直接推送代码到该 Space 仓库）。

### 5.3 配置 Secrets（Settings -> Variables and secrets）

建议添加：

- `OPENAI_API_KEY`
- `OPENAI_BASE_URL`（如 `https://api.openai.com/v1`）
- `OPENAI_MODEL`（如 `gpt-4o-mini`）

可选覆盖：

- `HOST`（默认 `0.0.0.0`）
- `PORT`（默认 `7860`）

### 5.4 部署与验证

代码推送后会自动触发构建，成功后打开 Space URL，检查：

- 首页可访问
- `GET /api/health` 返回 `checks.knowledge_base_ready: true`
- 对话接口可正常返回答案和证据

如果构建失败，优先检查：

- 是否错误上传了 `.venv` 或大文件（已通过 `.dockerignore` 规避）
- Secrets 是否完整
- `requirements.txt` 是否可成功安装

### 5.5 上线前检查清单（建议每次发布前执行）

- 健康检查：访问 `/api/health`，确认：
  - `checks.knowledge_base_ready = true`
  - `knowledge_base.exists = true`
  - `remote_llm_ready` 与你的预期一致（可开可关）
- Secrets 检查：
  - 已配置 `OPENAI_API_KEY`、`OPENAI_BASE_URL`、`OPENAI_MODEL`（如需远端自然语言增强）
  - 未在代码仓库提交 `.env`
- 启动体积检查：
  - `.dockerignore` 已忽略 `.venv`、日志、缓存目录
- 交互可用性检查：
  - 正常提问可返回
  - 服务异常时前端会显示可读错误（非空白/卡死）
  - 慢响应时会出现超时提示
- 回归问题抽查：
  - 模型支持类问题（如“Qwen3-32B 支持吗”）能返回结构化结果
  - 部署类问题（如“怎么上线到 HF Spaces”）能返回可执行建议

## 6) 官方来源

- [MindIE-LLM 支持模型列表](https://gitcode.com/Ascend/MindIE-LLM/blob/master/docs/zh/user_guide/model_support_list.md)

## 免责

内容用于技术参考，生产上线前请以华为昇腾与 MindIE 当前版本官方文档为准。
