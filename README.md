# 神志病AI双智能体临床思维训练系统 MVP

这是一个基于脱敏病例库的神志病双 Agent 临床思维训练系统：

- 患者Agent：根据病例角色卡模拟患者回答
- 督导Agent：基于关键词规则实时评分
- SOAP病历：根据问诊记录自动生成教学病历
- 本地运行：使用 Streamlit，可连接 DeepSeek API 或本地 Ollama

## 一、运行前准备

1. 安装 Python 3.11 或 3.12。
2. 在 `.streamlit/secrets.toml` 中配置 DeepSeek API Key，或安装 Ollama 并运行本地模型。

```bash
ollama pull qwen2.5:3b
ollama run qwen2.5:3b
```

如果电脑运行慢，可改用：

```bash
ollama pull qwen2.5:1.5b
```

## 二、启动项目

在 VS Code 打开本文件夹，然后在终端执行：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
./scripts/start_app.sh
```

打开浏览器后，选择病例，输入问诊问题即可。

## 三、演示前检查

在终端执行：

```bash
./scripts/run_pre_demo_check.sh
```

脚本会完成系统自检、自动回归测试和压力测试。随后按照
`docs/stability/演示前人工验收清单.md` 完成浏览器人工验收。

## 四、比赛演示建议

1. 先选择“病例1：肝郁脾虚证”
2. 问：你最近主要哪里不舒服？
3. 问：这种情况多久了？有什么诱因吗？
4. 问：睡眠和食欲怎么样？
5. 问：有没有不想活或者伤害自己的想法？
6. 问：舌象、脉象方便描述一下吗？
7. 点击“生成评分报告”和“生成SOAP病历”

## 五、项目目录

详见 `docs/项目目录说明.md`。

## 六、正式网页版部署

前端 React/Vite 和后端 Python API 可以拆成两个线上服务部署：

- `frontend/` 部署到 Vercel 或 Netlify。
- `api_server.py` 部署到 Render / Railway / Fly.io / 云服务器。

具体步骤见 `docs/正式网页版部署指南.md`。

## 七、注意事项

本系统仅用于医学教学训练，不用于真实诊疗。
