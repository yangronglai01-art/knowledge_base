# 评测体系（Gap #2）

本目录为 RAG 助手「掌柜智库」补齐的第二块短板——**评测体系**，包含：

- **测试集**（`dataset/`）：6 类知识、18 篇文档对应的问答对，以及权限过滤负例验证条目。
- **检索召回率评测**（`recall_at_k.py`）：评测向量检索的 Recall@K / Hit Rate@K、无结果率、权限过滤正确率。
- **生成质量评测**（`generation_quality.py`）：用 LLM 裁判评测答案的**忠实度（faithfulness）**与**正确性（correctness）**，并做规则性检查。

---

## 目录结构

```
tests/evaluation/
├── README.md                    # 本文档
├── evaluator_utils.py           # 公共工具：测试集加载、检索、命中判定
├── recall_at_k.py               # 检索召回率评测脚本
├── generation_quality.py        # 生成质量评测脚本
└── dataset/
    ├── 售后故障案例.json         # 3 条
    ├── 产品技术手册.json         # 3 条
    ├── 工艺规范.json             # 3 条
    ├── 质量制度.json             # 3 条
    ├── 设备操作维护.json         # 3 条
    ├── 业务流程.json             # 3 条
    └── 权限过滤验证.json         # 3 条负例（expect_hit=false）
```

---

## 前置条件

1. 已配置 `.env`（参考根目录 `.env.example`）：`MILVUS_URL`、`CHUNKS_COLLECTION`、`BGE_M3_*` 等。
2. Milvus 中已导入 `data/documents/` 对应的知识库切片。
3. 生成质量评测还需配置 LLM：`LLM_BASE_URL`、`LLM_API_KEY`、`LLM_MODEL`。

---

## 测试集格式

每个测试集是一个 JSON 文件，字段说明：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `schema_version` | string | 测试集格式版本（当前 1.0） |
| `category` | string | 知识类别 |
| `items` | array | 评测条目数组 |

每条评测条目（`items[]`）：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | string | 唯一编号，如 `aftersale-01` |
| `question` | string | 模拟用户问题 |
| `expected_hit_keywords` | string[] | 检索结果正文应命中的关键词（去空白后子串匹配，用于关键词命中率） |
| `expected_doc_titles` | string[] | 应命中的源文档标题（对应 Milvus 切片 `file_title` 字段，用于文档命中率） |
| `reference_answer` | string | 参考答案（用于生成质量评测的正确性打分） |
| `permission` | object | 模拟查询用户身份：`{departments: [...], clearance_level: int}` |
| `expect_hit` | bool | 是否期望命中目标文档；`false` 表示权限负例（目标文档应被拦截），默认 `true` |

---

## 检索召回率评测

指标定义：

- **文档命中率（Recall@K / Hit Rate@K）**：Top-K 结果中命中任意一篇期望源文档（`file_title` 精确匹配）的条目占比。
- **关键词命中率@K**：Top-K 结果正文命中任意一个期望关键词的条目占比。
- **无结果率**：Top-K 为空的条目占比。
- **权限过滤正确率**：`expect_hit=false` 负例中，目标文档确实未出现在 Top-K 的占比。

```bash
# 在项目根目录执行
python tests/evaluation/recall_at_k.py --k 5
python tests/evaluation/recall_at_k.py --k 10 --output reports/recall_at_k.md

# 覆盖用户身份（默认取测试集内 permission 字段）
python tests/evaluation/recall_at_k.py --departments 售后部 --clearance-level 3
```

---

## 生成质量评测

指标定义：

- **忠实度（faithfulness，1–5）**：答案是否由参考上下文（检索结果）支撑、有无编造。
- **正确性（correctness，1–5）**：答案与参考答案语义是否一致、是否覆盖关键事实点。
- **规则检查**：答案非空、长度合理。

流程：检索参考上下文 → 用 `ANSWER_PROMPT` 生成答案 → LLM 裁判分别对忠实度与正确性打分 → 规则检查。

```bash
python tests/evaluation/generation_quality.py --k 5
python tests/evaluation/generation_quality.py --k 5 --output reports/quality.md

# 调试：仅评测前 N 条 / 指定模型
python tests/evaluation/generation_quality.py --limit 2 --gen-model <生成模型> --judge-model <裁判模型>
```

---

## 说明

- 检索行为与线上查询链路（`node_search_embedding`）保持一致：混合检索权重 `(0.8, 0.2)`、`norm_score=True`、候选池默认 20。
- 评测脚本以 `python tests/evaluation/<script>.py` 方式运行（依赖脚本同目录的 `evaluator_utils`）。
- 权限过滤依赖 `permission_config.filter_enabled`；开启后按测试集内 `permission` 字段应用部门 + 密级过滤。
