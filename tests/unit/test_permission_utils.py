# tests/unit/test_permission_utils.py
"""权限过滤工具单元测试：验证 filter 表达式拼接逻辑（无需真实 Milvus）。"""
from knowledge_base.utils.permission_utils import (
    build_permission_filter,
    combine_filter,
)


def test_build_permission_filter_full():
    expr = build_permission_filter(departments=["销售部", "技术部"], clearance_level=3)
    assert '(dept in ["销售部", "技术部"] or dept == "*")' in expr
    assert "clearance_level <= 3" in expr


def test_build_permission_filter_dept_only():
    expr = build_permission_filter(departments=["销售部"], clearance_level=None)
    assert expr == '(dept in ["销售部"] or dept == "*")'


def test_build_permission_filter_clearance_only():
    expr = build_permission_filter(departments=None, clearance_level=5)
    assert expr == "clearance_level <= 5"


def test_build_permission_filter_empty():
    assert build_permission_filter() is None
    assert build_permission_filter(departments=[], clearance_level=None) is None


def test_build_permission_filter_escapes_special_chars():
    expr = build_permission_filter(departments=['部"门'], clearance_level=None)
    assert 'dept in ["部\\"门"]' in expr


def test_combine_filter_both():
    expr = combine_filter('item_name in ["A"]', '(dept in ["销售部"] or dept == "*")')
    assert expr == 'item_name in ["A"] and (dept in ["销售部"] or dept == "*")'


def test_combine_filter_single():
    assert combine_filter('item_name in ["A"]', None) == 'item_name in ["A"]'
    assert combine_filter(None, "clearance_level <= 3") == "clearance_level <= 3"
    assert combine_filter(None, None) is None
