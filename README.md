# 智能客服RAG系统

基于大语言模型与检索增强生成(RAG)的智能客服系统, 支持用户注册登录、文档上传管理、基于知识库的多轮智能问答, 并展示参考来源与相似度。

## 功能特性

- 用户体系: 注册 / 登录 / 退出 / 找回密码(JWT 鉴权, PBKDF2 密码哈希, 接口限流)
- 文档管理: 上传 PDF / TXT / MD, 内容去重, 列表 / 删除 / 一键清空(**按用户隔离**)
- 智能问答: 混合检索(向量相似度 + BM25 关键词) + 大模型生成, 返回参考来源与相似度
- 多轮对话: 按会话保存上下文, 支持清空会话历史
- 向量库: 默认内置本地向量库(零依赖, 无需 Docker); 配置后可切换为 Qdrant 服务
- 开箱即用: 默认使用 SQLite 数据库, 不依赖 MySQL 也能本地运行

## 技术栈

| 层 | 技术 |
| --- | --- |
| 后端 | Python 3.11+ / FastAPI / SQLAlchemy / Pydantic v2 / httpx / PyMuPDF |
| 检索 | 混合检索: 向量检索(qdrant-client, 可选) + BM25 关键词检索 |
| 向量化 | 内置离线向量化(默认); 也可接入 OpenAI 兼容的 `/v1/embeddings` 接口 |
| 大模型 | OpenAI 兼容接口(默认 `gpt-6-sol`) |
| 存储 | SQLite(默认) / MySQL 8 |
| 前端 | Vue 3 / Vite / Element Plus / Axios / Vue Router |
| 部署 | Docker / Docker Compose / Nginx |

## 目录结构

```
project04/
├── backend/                     # 后端服务
│   ├── app/
│   │   ├── api/                 # 路由: auth / documents / chat / deps
│   │   ├── core/                # 配置 / 数据库 / 安全(密码哈希)
│   │   ├── models/              # SQLAlchemy 模型与 Pydantic Schema
│   │   ├── services/            # RAG / 文档 / 向量库 / 向量化 / 大模型客户端
│   │   └── main.py              # 应用入口
│   ├── database/init.sql        # MySQL 初始化脚本
│   ├── verify.py                # 端到端接口自检脚本
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/                    # 前端应用
│   ├── src/
│   │   ├── components/          # Header / Login / Register / ChatInterface / DocumentManager
│   │   ├── services/            # api.js / auth.js
│   │   ├── store/               # 登录状态(响应式)
│   │   ├── router.js
│   │   ├── App.vue
│   │   └── main.js
│   ├── nginx.conf
│   ├── package.json
│   └── Dockerfile
├── docker-compose.yml           # 开发/测试编排(含 MySQL、Qdrant)
├── docker-compose.prod.yml      # 生产编排
├── start.bat / start.sh         # 一键启动脚本
├── .env.example                 # 环境变量示例
└── README.md
```

## 快速开始

### 方式一: 本地开发(推荐, 无需 Docker)

前置要求: Python 3.11+、Node.js 18+

```bash
# 1. 准备环境变量
cp .env.example .env
#    然后编辑 .env, 至少填写 API_KEY (大模型服务密钥)

# 2. 启动后端
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate   Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 3. 启动前端(另开一个终端)
cd frontend
npm install
npm run dev
```

访问地址:

- 前端: http://localhost:3000
- 后端 API 文档: http://localhost:8000/docs
- 健康检查: http://localhost:8000/health

> 默认使用 SQLite 与内置本地向量库, 无需安装 MySQL 或 Qdrant 即可完整运行。

### 方式二: Docker Compose 一键启动

```bash
cp .env.example .env    # 填写 API_KEY
./start.sh              # Linux/macOS
start.bat               # Windows
```

该方式会启动 MySQL、Qdrant、后端与前端四个容器, 前端地址为 http://localhost:3000。

生产环境:

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

## 配置说明

配置项位于 `.env`, 常用项如下:

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `API_KEY` | 空 | 大模型服务密钥, **必填** |
| `API_BASE_URL` | `https://token.uino.com/v1` | OpenAI 兼容接口地址 |
| `API_MODEL` | `gpt-6-sol` | 对话模型名称 |
| `EMBEDDING_PROVIDER` | `local` | `local` 内置离线向量化(零依赖) / `openai` 调用 embeddings 接口(语义效果更好) |
| `EMBEDDING_DIM` | `1024` | 内置向量化的向量维度 |
| `VECTOR_STORE_MODE` | `auto` | `auto` 优先 Qdrant 否则本地 / `local` 本地 / `qdrant` 强制 Qdrant |
| `DATABASE_URL` | `sqlite:///./rag_system.db` | 数据库连接串, 也可使用 MySQL |
| `CHUNK_SIZE` / `CHUNK_OVERLAP` | `500` / `80` | 文档切分粒度 |
| `TOP_K_RESULTS` | `4` | 检索返回条数 |
| `VECTOR_WEIGHT` / `KEYWORD_WEIGHT` | `0.6` / `0.4` | 混合检索权重 |
| `MAX_FILE_SIZE` | `10485760` | 单文件大小上限(字节) |
| `ALLOWED_EXTENSIONS` | `.pdf,.txt,.md` | 允许上传的文件类型 |
| `SECRET_KEY` | - | JWT 签名密钥, 生产环境务必修改 |
| `CORS_ORIGINS` | `*` | 允许的跨域来源, 多个用逗号分隔 |
| `RATE_LIMIT_ENABLED` | `True` | 是否开启接口限流 |
| `RATE_LIMIT_LOGIN` | `30/60` | 登录限流规则(次数/窗口秒), 按 IP+账号 计数 |
| `RATE_LIMIT_REGISTER` | `30/3600` | 注册限流规则(按 IP 计数) |
| `RATE_LIMIT_RESET_REQUEST` | `10/600` | 找回密码-请求验证码限流(按 IP+邮箱 计数) |
| `RATE_LIMIT_RESET_CONFIRM` | `20/600` | 找回密码-提交验证码限流(按 IP+邮箱 计数) |
| `RATE_LIMIT_CHAT` | `60/60` | 问答接口限流(按用户计数) |

## API 接口

除注册、登录、找回密码外, 所有接口都需要在请求头携带 `Authorization: Bearer <token>`。

### 用户认证

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/auth/register` | 注册并返回 token |
| POST | `/api/auth/login` | 登录(支持用户名或邮箱) |
| POST | `/api/auth/logout` | 退出登录 |
| GET | `/api/auth/me` | 获取当前用户信息 |
| POST | `/api/auth/reset-password` | 请求密码重置验证码 |
| POST | `/api/auth/reset-password/confirm` | 提交验证码与新密码 |

### 文档管理

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/documents/upload` | 上传文档(相同内容自动去重) |
| GET | `/api/documents` | 文档列表 |
| GET | `/api/documents/stats` | 知识库统计 |
| DELETE | `/api/documents/{id}` | 删除文档及其向量 |
| POST | `/api/documents/clear` | 清空全部文档 |

### 智能问答

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/chat` | 提问, 返回答案与参考来源 |
| GET | `/api/chat/history/{session_id}` | 会话历史 |
| DELETE | `/api/chat/history/{session_id}` | 清空指定会话 |
| DELETE | `/api/chat/history` | 清空全部会话 |

## 安全设计

| 机制 | 说明 |
| --- | --- |
| 密码存储 | 标准库 PBKDF2-HMAC-SHA256, 26 万次迭代 + 每用户随机盐, 常量时间比较 |
| 接口鉴权 | JWT(HS256) Bearer Token, 除注册/登录/找回密码外全部接口强制校验 |
| 接口限流 | 内存滑动窗口限流, 覆盖注册 / 登录 / 找回密码 / 问答, 超限返回 429 并带 `Retry-After` |
| 数据隔离 | 文档与向量都携带 `owner_id`, 每个用户只能访问自己的知识库与会话历史 |
| 会话归属 | 会话历史绑定创建者, 跨用户读取/清空一律无效, 复用他人 session_id 会被分配新会话 |
| 错误信息 | 后端异常只记录到日志, 响应统一返回通用提示, 不泄露堆栈 / 路径 / SQL 细节 |
| 文件安全 | 存储文件名由服务端按 用户ID+内容哈希 生成, 不使用用户提供的路径, 天然防目录穿越 |
| CORS | 配置为 `*` 时自动关闭 `allow_credentials`, 避免浏览器拒绝非法组合 |

> 限流计数保存在进程内存中, 适用于单实例部署; 多实例部署需替换为 Redis 等集中式存储。

## 自检验证

后端提供端到端自检脚本, 启动后端后执行:

```bash
cd backend
python verify.py
```

脚本会依次校验注册/登录/鉴权、文档上传(去重/类型校验/PDF/MD)、混合检索问答、会话历史、密码重置、删除与清空、**用户隔离与限流**等 40 项行为, 并输出 PASS/FAIL 汇总。

## 生产部署

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

生产环境请注意:

1. 修改 `SECRET_KEY` 与数据库密码, 使用强随机值;
2. 将 `DEBUG` 设为 `False`;
3. 将 `CORS_ORIGINS` 限制为实际前端域名;
4. 前端建议置于 HTTPS 反向代理之后。