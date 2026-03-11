![vSkin](https://socialify.git.ci/LYOfficial/vSkin/image?description=1&font=Inter&forks=1&language=1&name=1&owner=1&stargazers=1&theme=Auto)

# vSkin 皮肤站

> 一个基于 Vue 3 + FastAPI 的 Minecraft 外置登录与皮肤管理系统，支持 Yggdrasil 协议、站点用户系统、材质管理与后台运维。

开源地址：<https://github.com/LYOfficial/vSkin>

## 功能特性

* **单容器部署**：前端构建产物直接打包进后端镜像，使用一个容器同时提供页面、静态资源与 API，减少跨容器转发导致的登录、注册和回调异常。
* **完整协议支持**：兼容 Yggdrasil 协议，可直接对接 Authlib-Injector 与常见启动器。
* **用户系统完整**：支持注册、登录、密码找回、邮箱验证码、邀请码注册与 JWT 鉴权。
* **材质管理完善**：支持皮肤与披风上传、公开材质库、角色绑定，以及 3D 预览。
* **方形头像系统**：默认使用 Steve 头部平面头像；用户可从已上传/已收藏皮肤中一键截取正脸设为头像。
* **后台能力充足**：支持站点设置、用户管理、邮件服务、轮播图、Fallback 节点配置等常见运维需求。
* **OAuth 2 对外登录**：支持管理员创建外部应用（appid/secret/回调地址），外部网站可通过 vSkin 账号完成授权登录。
* **可扩展部署**：默认推荐根路径部署，也支持前端子路径部署。

> 注意：默认 Docker 方案会将后端 API 固定暴露在 `/skinapi/*` 下，以避免和前端 SPA 路由冲突。

### 技术栈

[![Vue](https://img.shields.io/badge/Vue-3-42B883?style=for-the-badge&logo=vuedotjs&logoColor=white)](https://vuejs.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?style=for-the-badge&logo=docker&logoColor=white)](https://www.docker.com/)

## 开始使用

如果你只是想部署并使用 vSkin，推荐直接使用仓库根目录的 `docker-compose.yml` 进行构建和启动。

vSkin 当前推荐以下运行方式：

| 方式 | 说明 | 适用场景 |
|------|------|----------|
| Docker Compose | 单容器部署前后端 | 生产环境、测试环境 |
| 本地开发 | 前端 Vite + 后端 Uvicorn 分别启动 | 二次开发、调试 |

## Docker Compose 部署

### 部署说明

当前仓库已经调整为单容器架构：

* 前端在镜像构建阶段完成打包。
* 后端运行时直接托管前端页面与 `/static/*` 静态资源。
* 所有 API 路径统一位于 `/skinapi/*`。
* 对外只需要暴露一个 `8000` 端口。

这意味着你不再需要分别处理前端容器和后端容器，也不需要担心跨端口访问、Cookie/回调地址错乱、反向代理遗漏导致的无法注册或无法登录问题。

### 准备配置文件

先在项目根目录创建或修改 `config.yaml`：

```yaml
jwt:
  secret: "CHANGE-ME-TO-A-LONG-RANDOM-SECRET"

keys:
  private_key: "/data/private.pem"
  public_key: "/data/public.pem"

database:
  path: "/data/yggdrasil.db"

textures:
  directory: "/data/textures"

carousel:
  directory: "/data/carousel"

server:
  host: "0.0.0.0"
  port: 8000
  root_path: ""
  site_url: "https://skin.example.com"
  api_url: "https://skin.example.com/skinapi"

cors:
  allow_origins:
    - "https://skin.example.com"
  allow_credentials: true

mojang:
  session_url: "https://sessionserver.mojang.com"
  account_url: "https://api.mojang.com"
  services_url: "https://api.minecraftservices.com"
  skin_domains:
    - "textures.minecraft.net"
  cache_ttl: 3600
```

> 注意：`server.site_url` 必须填写你实际访问站点的外部地址，`server.api_url` 必须填写对应的 `/skinapi` 地址，否则微软登录回调、材质地址和部分前端请求会异常。

### 使用 Docker Compose 启动

项目根目录中的 `docker-compose.yml` 已可直接使用：

```yaml
version: '3.8'

services:
  app:
    build:
      context: .
      dockerfile: skin-backend/Dockerfile
      args:
        - VITE_BASE_PATH=/
        - VITE_API_BASE=/skinapi
        - BUILD_MODE=standard
    container_name: vskin
    restart: unless-stopped
    ports:
      - "8000:8000"
    volumes:
      - ./config.yaml:/app/config.yaml:ro
      - ./data:/data
    environment:
      - SERVER__ROOT_PATH=/skinapi
```

然后执行：

```bash
docker compose up -d --build
```

启动完成后：

* 站点首页默认访问 `http://你的服务器:8000/`
* 后端 API 默认访问 `http://你的服务器:8000/skinapi/`

### 低内存机器构建

如果服务器内存较小，可以在构建时切换低内存模式：

```bash
BUILD_MODE=low-memory docker compose up -d --build
```

### 前端子路径部署

如果你需要把前端部署到子路径，例如 `https://example.com/skin/`，可以这样启动：

```bash
VITE_BASE_PATH=/skin/ VITE_API_BASE=/skinapi docker compose up -d --build
```

这种模式下：

* 前端页面地址为 `/skin/`
* 后端 API 仍然保持 `/skinapi/*`

这样做的目的是保持 API 路径稳定，不去和前端路由共享同一个路径前缀。

### 反向代理示例

如果你使用 Nginx 反向代理域名，只需要把所有请求转发给容器的 `8000` 端口：

```nginx
server {
    listen 80;
    server_name skin.example.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### 初始化使用

首次启动后，建议按以下顺序完成初始化：

1. 访问站点首页并注册第一个账户。
2. 第一个注册账户会自动成为管理员。
3. 登录后台后完成站点设置、邮件服务和注册策略配置。
4. 检查 `config.yaml` 中的 `site_url` 与 `api_url` 是否已经替换为正式域名。
5. 如需外部站点接入登录，进入后台的「OAuth 应用」页面创建应用并保存 `client_secret`。

### OAuth 2 对接说明

管理员在后台 `OAuth 应用` 中创建应用后，会获得以下信息：

* `appid`（即 `client_id`，从 1 开始自动递增）
* `client_secret`（自动生成，仅创建/重置时完整展示）
* `redirect_uri`（你填写的回调地址）

授权流程（Authorization Code）：

1. 外部网站将用户跳转到：`https://你的站点/oauth/authorize?client_id={appid}&redirect_uri={redirect_uri}&state={state}&scope={scope}`
2. 用户在 vSkin 页面登录并确认授权。
3. vSkin 回跳到 `redirect_uri`，并附带 `code`（以及原始 `state`）。
4. 外部网站向令牌接口提交表单：
  * `POST {api_url}/oauth/token`
  * `grant_type=authorization_code`
  * `code={code}`
  * `client_id={appid}`
  * `client_secret={client_secret}`
  * `redirect_uri={redirect_uri}`
5. 使用返回的 `access_token` 调用：`GET {api_url}/oauth/userinfo`，并带上 `Authorization: Bearer {access_token}`。

授权页说明：

* 用户授权页仅展示「{第三方站点} 请求以 {本站} 登录」及权限列表（scope）。
* 不再向用户展示 appid、回调地址等技术参数。
* 用户只需同意授权或拒绝授权。

推荐 scope：

* `userinfo`：用户基础信息（用户ID、用户名、头像）
* `profile`：用户名
* `avatar`：头像地址
* `email`：邮箱

可用接口（均需 `Authorization: Bearer {access_token}`）：

* `GET {api_url}/oauth/userinfo`：按 scope 返回综合信息（如 `sub`、`username`、`avatar_url`、`email`）
* `GET {api_url}/oauth/profile`：用户名信息接口
* `GET {api_url}/oauth/avatar`：头像信息接口
* `GET {api_url}/oauth/email`：邮箱信息接口

头像相关接口：

* `POST {api_url}/me/avatar/from-texture`：从用户已拥有皮肤截取头部正脸并设为头像
* `GET {api_url}/public/default-avatar`：默认 Steve 头部方形头像

说明：

* `api_url` 对应配置中的 `server.api_url`（通常是 `https://域名/skinapi`）。
* `redirect_uri` 必须与后台配置完全一致（包括路径与大小写）。

## 本地开发与贡献

首先克隆本项目：

```bash
git clone https://github.com/LYOfficial/vSkin.git
cd vSkin
```

### 后端开发

```bash
cd skin-backend
python -m venv .venv

# Windows
.venv\Scripts\activate

# Linux / macOS
source .venv/bin/activate

pip install -r requirements.txt
python gen_key.py
uvicorn routes_reference:app --reload
```

### 前端开发

```bash
cd vskin
npm install
npm run dev
```

开发环境下前端默认访问：<http://localhost:5173>

## 项目结构

```text
vSkin/
├── vskin/               # Vue 3 前端
├── skin-backend/        # FastAPI 后端
├── config.yaml          # 宿主机配置文件
├── docker-compose.yml   # Docker Compose 编排文件
├── nginx-host.conf      # 反向代理配置示例
└── data/                # 数据目录（数据库、密钥、材质、轮播图）
```

## 自动化测试

项目包含数据库层、后端逻辑层和 API 层测试。

运行方式：

```bash
cd skin-backend
pytest tests/
```

如果只是验证接口层：

```bash
cd skin-backend
pytest tests/api -q
```

## 鸣谢

vSkin 的设计与实现参考了以下开源项目，在此致谢：

* <https://github.com/water2004/element-skin>
* <https://github.com/bs-community/blessing-skin-server>

## 许可证

[GPL-3.0 license](LICENSE)