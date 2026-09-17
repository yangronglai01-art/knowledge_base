# 知识库内容包（一期 · 案例替换）

本目录存放可导入 RAG 知识库「掌柜智库」的**脱敏企业案例文档**，用于替换原空内容，覆盖规划 4.1 一期覆盖清单。

所有内容均为**虚构 / 脱敏**案例，不涉及任何真实敏感数据；产品型号、客户名称、人名、批次号等均为示例占位。

## 目录结构

```
data/documents/
├── README.md                 # 本说明（导入方式）
├── manifest.json             # 文档权限元数据清单（机器可读）
├── manifest.csv              # 文档权限元数据清单（表格视图）
├── 售后故障案例/             # 售后故障案例（售后部）
├── 产品技术手册/             # 产品技术手册节选（技术部 / 公开）
├── 工艺规范/                 # 工艺规范（生产部）
├── 质量制度/                 # 质量制度（质量部）
├── 设备操作维护/             # 设备操作维护资料（设备部 / 生产部）
└── 业务流程/                 # 常用业务流程（售后部 / 销售部 / 生产部）
```

## 权限模型（与短板#1 一致）

每篇文档标注两个权限字段，与 Milvus `chunks` 集合字段严格对应：

| 字段 | 类型 | 取值 | 说明 |
| --- | --- | --- | --- |
| `dept` | VARCHAR | `销售部` / `技术部` / `生产部` / `质量部` / `售后部` / `设备部` 或 `*` | 文档所属部门；`*` 表示**全员可访问** |
| `clearance_level` | INT8 | `1` ~ `5` | 密级，**越大越机密**；用户仅能命中 `clearance_level <= 自身密级` 的文档 |

检索时的权限过滤表达式（由 `permission_utils.build_permission_filter` 生成）示例：

```
(dept in ["售后部", "销售部"] or dept == "*") and clearance_level <= 3
```

即：**文档部门 ∈ 用户部门（或文档为公开 `*`）且 文档密级 ≤ 用户密级**。

## 如何导入

`/upload` 接口在接收文件的同时，通过表单字段透传权限元数据：

| 表单字段 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `file` | file | — | 文档文件（本目录下 `.md`） |
| `dept` | str | `*` | 文档所属部门，`*` = 全员公开 |
| `clearance_level` | int | `1` | 文档密级 1-5 |

### 批量导入示例（PowerShell）

按 `manifest.csv` / `manifest.json` 中的标注逐条上传：

```powershell
# 以单篇为例：导入售后故障案例（售后部，密级 2）
$file = "data\documents\售后故障案例\售后故障案例-BSL系列螺杆空压机高温报警处理.md"
curl.exe -X POST "http://localhost:8000/upload" `
  -F "file=@$file;type=text/markdown" `
  -F "dept=售后部" `
  -F "clearance_level=2"
```

### 批量导入脚本（可复用）

依据 `manifest.json` 循环导入：

```python
import json
from pathlib import Path
import requests

base = Path("data/documents")
manifest = json.loads((base / "manifest.json").read_text(encoding="utf-8"))

for doc in manifest["documents"]:
    fp = base / doc["file"]
    with fp.open("rb") as f:
        r = requests.post(
            "http://localhost:8000/upload",
            files={"file": (fp.name, f, "text/markdown")},
            data={
                "dept": doc["dept"],
                "clearance_level": doc["clearance_level"],
            },
        )
    print(doc["title"], doc["dept"], doc["clearance_level"], "->", r.status_code)
```

## 文档清单概览

| 类别 | 数量 | 主要部门 | 密级区间 |
| --- | --- | --- | --- |
| 售后故障案例 | 3 | 售后部 | 2 |
| 产品技术手册节选 | 3 | 技术部 / 公开(`*`) | 1–3 |
| 工艺规范 | 3 | 生产部 | 3–4 |
| 质量制度 | 3 | 质量部 | 2–3 |
| 设备操作维护资料 | 3 | 设备部 / 生产部 | 2–3 |
| 常用业务流程 | 3 | 售后部 / 销售部 / 生产部 | 1 |

> 说明：`*` 表示全员公开（示例见「产品技术手册-BSL系列空压机产品概述.md」），
> 用于验证「公开文档对任意部门用户可见」的权限分支。
