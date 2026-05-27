# 第二层生成式训练样本使用说明

本目录保存由 234 例脱敏标准病例表自动构造的生成式训练样本，用于患者 Agent、督导 Agent、SOAP Agent 的训练、评估和稳定性测试。

这些数据仅用于医学教学训练和系统研发，不用于真实诊疗。

## 一、文件总览

| 文件 | 数量 | 主要用途 |
| --- | ---: | --- |
| `all_dialogues.jsonl` | 1170 | 全量多轮问诊样本，包含训练集和验证集 |
| `train_dialogues.jsonl` | 940 | 训练集多轮问诊样本 |
| `val_dialogues.jsonl` | 230 | 验证集多轮问诊样本，用于评估，不建议参与训练 |
| `train_patient_agent_sft.jsonl` | 5452 | 患者 Agent 单轮 SFT/微调训练样本 |
| `val_patient_agent_sft.jsonl` | 1334 | 患者 Agent 单轮验证样本 |
| `train_supervisor_refs.jsonl` | 940 | 督导评分参考答案训练数据 |
| `val_supervisor_refs.jsonl` | 230 | 督导评分参考答案验证数据 |
| `train_soap_refs.jsonl` | 940 | SOAP 病历参考答案训练数据 |
| `val_soap_refs.jsonl` | 230 | SOAP 病历参考答案验证数据 |
| `manifest.json` | 1 | 数据来源、数量和生成摘要 |

文件格式均为 JSONL，即每一行都是一个独立 JSON 对象。读取时应逐行解析，不要把整个文件当作一个 JSON 数组读取。

## 二、样本类型

每个病例构造 5 种问诊样本：

| `sample_type` | 含义 |
| --- | --- |
| `standard_full_interview` | 标准完整问诊，覆盖主诉、病程、睡眠饮食、风险、鉴别、舌脉和总结 |
| `risk_screening_focus` | 风险筛查重点样本，强化自杀自伤、计划、保护因素等问题 |
| `tcm_information_focus` | 中医信息采集重点样本，强化情志、睡眠、饮食二便、寒热汗、舌脉 |
| `differential_diagnosis_focus` | 鉴别诊断重点样本，强化躁狂/双相、精神病性症状、躯体疾病和药物因素 |
| `incomplete_interview_for_scoring` | 不完整问诊样本，用于训练/测试督导评分发现遗漏 |

## 三、`*_dialogues.jsonl` 的结构

`train_dialogues.jsonl`、`val_dialogues.jsonl` 和 `all_dialogues.jsonl` 每一行的核心结构如下：

```json
{
  "sample_id": "case_001_01_standard_full_interview",
  "case": {
    "case_id": "case_001",
    "split": "训练集",
    "chief_complaint": "...",
    "syndrome": "...",
    "diagnosis_category": "...",
    "risk_level": "...",
    "tongue": "...",
    "pulse": "...",
    "tongue_image": "case_001.jpg"
  },
  "sample_type": "standard_full_interview",
  "dialogue": [
    {
      "doctor": "你最近主要哪里不舒服？",
      "patient": "最近主要是..."
    }
  ],
  "supervisor_reference": {},
  "soap_reference": {},
  "patient_agent_constraints": {}
}
```

推荐用途：

- 用 `train_dialogues.jsonl` 构造多轮问诊训练任务。
- 用 `val_dialogues.jsonl` 测试当前患者 Agent 是否回答稳定、是否遗漏、是否泄露诊断/证型。
- 用 `all_dialogues.jsonl` 做数据统计、病例覆盖分析或演示样本抽取。

## 四、患者 Agent 微调数据

`train_patient_agent_sft.jsonl` 和 `val_patient_agent_sft.jsonl` 是单轮对话微调格式，每一行都包含 `messages`：

```json
{
  "sample_id": "case_001_01_standard_full_interview_turn_01",
  "case_id": "case_001",
  "messages": [
    {
      "role": "system",
      "content": "你正在扮演一名中医精神心理方向的模拟患者..."
    },
    {
      "role": "user",
      "content": "既往对话：..."
    },
    {
      "role": "assistant",
      "content": "患者回答..."
    }
  ]
}
```

推荐用途：

- 后续微调患者 Agent 时，训练集使用 `train_patient_agent_sft.jsonl`。
- 验证集使用 `val_patient_agent_sft.jsonl`。
- 患者回答中已经避免主动暴露证型、诊断大类、量表名称和量表分数。

注意：这批数据适合训练“模拟患者怎么回答”，不适合直接训练真实诊疗建议模型。

## 五、督导评分参考数据

`train_supervisor_refs.jsonl` 和 `val_supervisor_refs.jsonl` 每一行对应一个问诊样本的评分参考：

```json
{
  "sample_id": "case_001_01_standard_full_interview",
  "case_id": "case_001",
  "score_result": {
    "问诊完整性": {
      "score": 20,
      "weight": 25,
      "hit": [],
      "miss": []
    }
  },
  "total_score": 72.0,
  "required_questions": [],
  "main_gaps": [],
  "ideal_next_questions": []
}
```

推荐用途：

- 训练或评估督导 Agent 是否能指出学生问诊遗漏。
- 对比当前 MVP 中规则评分的输出是否稳定。
- 用 `val_supervisor_refs.jsonl` 做评分回归测试。

## 六、SOAP 参考数据

`train_soap_refs.jsonl` 和 `val_soap_refs.jsonl` 每一行对应一个问诊样本的 SOAP 参考：

```json
{
  "sample_id": "case_001_01_standard_full_interview",
  "case_id": "case_001",
  "soap_reference": {
    "S": {},
    "O": {},
    "A": {},
    "P": [],
    "teaching_note": "本记录为模拟教学参考，不用于真实诊疗。"
  }
}
```

推荐用途：

- 训练 SOAP Agent 按“已问到的信息”生成病历。
- 测试 SOAP Agent 是否会把未问到内容写成“未询及”。
- 测试 SOAP Agent 是否会误写真实处方或真实诊疗建议。

## 七、当前 MVP 中的推荐使用流程

### 1. 测试患者 Agent 稳定性

读取 `val_dialogues.jsonl`，逐个取出 `dialogue` 中的医生问题，喂给当前 MVP 的患者 Agent。

重点观察：

- 是否严格按病例信息回答。
- 是否不主动透露证型、诊断、量表分数。
- 是否能在风险筛查、舌象、脉象问题中给出合理回答。
- 多轮上下文是否一致。

### 2. 测试督导 Agent 或规则评分

读取 `val_dialogues.jsonl` 的 `dialogue`，再读取同一条样本里的 `supervisor_reference`。

对比：

- 总分是否接近。
- 命中的问诊维度是否一致。
- 遗漏项是否能被指出。
- 对不完整样本是否能给出明确补问建议。

### 3. 测试 SOAP 生成

读取 `val_dialogues.jsonl` 的 `dialogue`，让 SOAP Agent 生成病历，再与 `soap_reference` 对比。

重点检查：

- 未问到的信息是否写为“未询及”。
- 是否把教学辨证和真实诊疗区分开。
- 是否避免真实处方。
- 风险评估和中医四诊是否有条理。

## 八、Python 读取示例

```python
import json
from pathlib import Path

path = Path("/Users/qymeded/Documents/神志病AI/training_samples/val_dialogues.jsonl")

with path.open("r", encoding="utf-8") as f:
    for line in f:
        sample = json.loads(line)
        sample_id = sample["sample_id"]
        case_id = sample["case"]["case_id"]
        dialogue = sample["dialogue"]
        supervisor_ref = sample["supervisor_reference"]
        soap_ref = sample["soap_reference"]

        print(sample_id, case_id, len(dialogue), supervisor_ref["total_score"])
        break
```

## 九、训练和验证边界

建议保持以下边界：

- `train_*` 只用于训练、提示词优化、微调。
- `val_*` 只用于评估，避免混入训练。
- `all_dialogues.jsonl` 只用于统计、抽样和人工浏览。
- 如果后续重新生成样本，应同步更新 `manifest.json`。

## 十、与第一层病例 JSON 的关系

第一层病例 JSON 是系统运行时的病例库。

第二层训练样本是基于病例库构造出来的教学问诊样本。

两者关系如下：

```text
标准病例表
  -> 第一层：病例 JSON，用于 MVP 运行时选择病例
  -> 第二层：训练样本 JSONL，用于训练、评估、微调和回归测试
```

舌象图片不会直接进入 JSONL，只保留匿名图片文件名，例如 `case_001.jpg`。图片应由第一层病例 JSON 和项目的 `tongue_images` 目录负责绑定展示。

