# Director AI

Director AI 是一个面向短片、漫剧、广告分镜和视频创作的 AI 分镜生产工具。项目当前以 `web/` 下的 Gradio 应用为主，支持从一句话故事生成角色、场景、镜头、图像提示词，并继续生成分镜图和镜头视频。

## 核心功能

- **一句话生成故事**：接入 Qwen OpenAI-compatible 文本模型，从故事创意自动生成项目名称、剧情简介、角色、场景、道具和 7 个分镜。
- **自动生成分镜提示词**：每个镜头会生成 `generated_prompt` 和结构化 `standard_prompt`，用于后续图像生成。
- **分镜图生成**：默认使用 SeedreamBest 同款 MuleRouter / Wan 链路，图像模型为 `wan2.6-t2i`。
- **视频生成**：支持图生视频和文生视频，默认使用 `wan2.7-i2v-spicy`，可对单个镜头、选中镜头或全部镜头生成视频。
- **选择式生产流程**：支持生成单张、全部生成、视频单选/多选、加载历史图片、加载已生成视频和刷新状态。
- **API 渠道状态面板**：展示图像、视频、文字模型渠道状态，方便检查 key、模型和接口是否可用。
- **ComfyUI 回退**：云端生成优先，ComfyUI 可作为本地视频/图像生成回退链路。
- **项目保存与加载**：自动保存项目数据，支持恢复角色、场景、镜头、图片和视频路径。

## 模型链路

当前默认链路如下：

| 能力 | 默认服务 | 默认模型 / 路由 |
| --- | --- | --- |
| 文字生成 | Qwen OpenAI-compatible API | `QWEN_LLM_MODEL` |
| 图像生成 | MuleRouter / SeedreamBest 同款 | `wan2.6-t2i` |
| 图像无参考图 | MuleRouter | `carrothub/z-image-spicy` |
| 图像参考图编辑 | MuleRouter | `carrothub/qwen-image-edit-spicy` |
| 图生视频 | MuleRouter | `carrothub/wan2.7-i2v-spicy` |
| 文生视频 | MuleRouter | `alibaba/wan2.6-t2v` |
| 本地回退 | ComfyUI | 自定义 workflow |

## 快速启动

进入 Web 应用目录：

```bash
cd web
```

创建虚拟环境并安装依赖：

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

复制环境配置：

```bash
cp .env.example .env
```

编辑 `.env`，填入自己的 API Key。不要把 `.env` 提交到 Git。

启动 Gradio：

```bash
.venv/bin/python app.py
```

默认访问地址：

```text
http://127.0.0.1:7861
```

## GitHub Actions 部署

项目已提供 GitHub Actions 部署 workflow：[.github/workflows/deploy.yml](.github/workflows/deploy.yml)。

推送到 `master` 或手动触发 workflow 后，Actions 会通过 SSH 登录服务器，在 `/opt/MoyinEngine_ai` 拉取最新代码，安装 `web/requirements.txt`，并通过 systemd 管理 `director-ai` 服务。

需要在 GitHub 仓库 `Settings -> Secrets and variables -> Actions` 中配置：

```text
DEPLOY_HOST=35.220.200.97
DEPLOY_USER=huangguojie
DEPLOY_SSH_KEY=<服务器私钥内容>
DEPLOY_PORT=22
```

服务器上的运行目录：

```text
/opt/MoyinEngine_ai
```

服务管理命令：

```bash
sudo systemctl status director-ai
sudo systemctl restart director-ai
sudo journalctl -u director-ai -f
```

## 环境变量

常用配置项：

```env
# 图像 / 视频生成
MULEROUTER_API_KEY=your_mulerouter_api_key_here
MULEROUTER_BASE_URL=https://api.mulerouter.ai
SEEDREAMBEST_IMAGE_PROVIDER_MODEL=wan2.6-t2i
SEEDREAMBEST_VIDEO_PROVIDER_MODEL=wan2.7-i2v-spicy

# 文字生成
LLM_PROVIDER=Qwen (OpenAI兼容)
QWEN_API_KEY=your_qwen_api_key_here
QWEN_BASE_URL=http://your-qwen-host:8000/v1
QWEN_LLM_MODEL=your-qwen-model-id

# 本地回退
COMFYUI_ENABLED=false
COMFYUI_HOST=127.0.0.1
COMFYUI_PORT=8188
```

完整配置见 [web/.env.example](web/.env.example)。

## 使用流程

1. 在“一句话生成故事”输入故事创意，点击 `AI 生成`。
2. 系统会自动生成角色、场景、7 个镜头和每个镜头的图像提示词。
3. 进入“生成”区域，选择单个镜头或点击全部生成，生成分镜图。
4. 进入“视频生成”区域，选择一个或多个已有图片的镜头，生成视频。
5. 使用“加载视频”或“刷新”同步视频卡片和预览。

## 项目结构

```text
director_ai/
├── README.md                 # 项目说明
├── web/                      # Gradio Web 主应用
│   ├── app.py                # 主界面和流程编排
│   ├── ai_creative_generator.py
│   ├── image_generator.py
│   ├── mulerouter_providers.py
│   ├── settings.py
│   ├── requirements.txt
│   └── .env.example
├── lib/                      # Flutter/移动端相关代码
├── android/                  # Android 工程
├── images/                   # 示例或历史素材
└── docs/                     # 文档资料
```

## 安全说明

- `.env` 已在 `.gitignore` 中忽略，请只提交 `.env.example`。
- 不要把 MuleRouter、Qwen 或其他服务的真实 API Key 写入 README、代码或提交记录。
- 生成的图片、视频、项目缓存通常包含用户内容，默认应保留在本地。

## 当前状态

项目当前主要工作流已打通：

- Qwen 文本生成
- Wan 图像生成
- Wan 视频生成
- 单选/多选镜头视频生成
- 图片与视频加载、预览和状态刷新
