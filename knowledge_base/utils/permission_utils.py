# knowledge_base/utils/permission_utils.py
"""文档权限过滤工具：统一构建 Milvus 权限 filter 表达式。

权限模型（轻量，预留企业 SSO 接口）：
- 文档导入时携带两个权限字段：
  - dept（部门）：文档所属部门，取 PUBLIC_DEPT 表示全员可访问。
  - clearance_level（密级）：整数 1-5，数值越大越机密。
- 查询用户携带：
  - departments：用户所属部门列表。
  - clearance_level：用户密级，可访问 clearance_level <= 自身密级 的文档。

过滤规则：文档 dept 在用户部门列表内（或为公共部门），且文档密级 <= 用户密级。

说明：本模块刻意不依赖 pymilvus，便于纯逻辑单元测试。
"""
from typing import List, Optional

# 公共部门标识：文档归属该值时，所有部门用户均可访问
PUBLIC_DEPT = "*"

# 默认公开密级（最小限制）
PUBLIC_CLEARANCE = 1


def _escape(value: str) -> str:
    """特殊字符转义，与 milvus_utils.escape_milvus_string 保持一致。"""
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("'", "\\'")


def build_permission_filter(
    departments: Optional[List[str]] = None,
    clearance_level: Optional[int] = None,
) -> Optional[str]:
    """构建权限过滤表达式。

    :param departments: 用户所属部门列表；为空表示不限制部门（密级仍限制）
    :param clearance_level: 用户密级；为空表示不限制密级
    :return: Milvus filter 表达式；两者均为空时返回 None（表示不做权限限制）
    """
    conditions = []

    if departments:
        escaped = ", ".join(f'"{_escape(d)}"' for d in departments)
        conditions.append(f'(dept in [{escaped}] or dept == "{PUBLIC_DEPT}")')

    if clearance_level is not None:
        conditions.append(f"clearance_level <= {int(clearance_level)}")

    if not conditions:
        return None
    return " and ".join(conditions)


def combine_filter(
    item_filter: Optional[str],
    permission_filter: Optional[str],
) -> Optional[str]:
    """合并业务过滤（如 item_name）与权限过滤，用 and 连接。"""
    parts = [p for p in (item_filter, permission_filter) if p]
    if not parts:
        return None
    return " and ".join(parts)
