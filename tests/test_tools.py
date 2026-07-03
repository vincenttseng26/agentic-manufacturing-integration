"""Phase 3/6：tools 的唯讀防護 + JSON 轉換單元測試（不需 DB / Gemini，CI 直接可跑）。"""
import datetime
import decimal
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parents[1]))
from orchestration import tools  # noqa: E402


@pytest.mark.parametrize("bad_sql", [
    "DROP TABLE jobs",
    "UPDATE jobs SET success = true",
    "DELETE FROM jobs",
    "SELECT 1; DELETE FROM jobs",  # 多段語句
])
def test_query_db_rejects_non_readonly(bad_sql):
    """非唯讀 / 多段語句應在打到 DB 前就被擋下。"""
    with pytest.raises(ValueError):
        tools.query_db(bad_sql)


def test_jsonable_converts_decimal_and_datetime():
    assert tools._jsonable(decimal.Decimal("1.5")) == 1.5
    assert isinstance(tools._jsonable(decimal.Decimal("1.5")), float)
    assert tools._jsonable(datetime.date(2026, 7, 2)) == "2026-07-02"
    assert tools._jsonable("unchanged") == "unchanged"
