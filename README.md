# 神志病AI双智能体临床思维训练系统 MVP

这是一个适合10天参赛演示的最小可运行版本：

- 患者Agent：根据病例角色卡模拟患者回答
- 督导Agent：基于关键词规则实时评分
- SOAP病历：根据问诊记录自动生成教学病历
- 本地运行：使用 Streamlit + Ollama

## 一、运行前准备

1. 安装 Python 3.11 或 3.12
2. 安装 Ollama，并先运行一个小模型，例如：

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
streamlit run app.py
```

打开浏览器后，选择病例，输入问诊问题即可。

## 三、比赛演示建议

1. 先选择“病例1：肝郁脾虚证”
2. 问：你最近主要哪里不舒服？
3. 问：这种情况多久了？有什么诱因吗？
4. 问：睡眠和食欲怎么样？
5. 问：有没有不想活或者伤害自己的想法？
6. 问：舌象、脉象方便描述一下吗？
7. 点击“生成评分报告”和“生成SOAP病历”

## 四、注意事项

本系统仅用于医学教学训练，不用于真实诊疗。
