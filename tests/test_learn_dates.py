import datetime

import pytest

import learn
from learn_support import DS, make_root, run_main, snapshot

DT = datetime.datetime


def test_O18_D1_iso_date_unchanged():
    assert learn.parse_date("2026-02-28", now=DT(2026, 11, 5, 12, 0)) == datetime.date(2026, 2, 28)


@pytest.mark.parametrize(
    "now,expected",
    [
        (DT(2026, 11, 5, 4, 59), datetime.date(2026, 11, 4)),
        (DT(2026, 11, 5, 5, 0), datetime.date(2026, 11, 5)),
    ],
    ids=["D2_0459", "D3_0500"],
)
def test_O18_D2_D3_today_rollover(now, expected):
    assert learn.parse_date("today", now=now) == expected


@pytest.mark.parametrize(
    "now,expected",
    [
        (DT(2026, 11, 5, 4, 59), datetime.date(2026, 11, 3)),
        (DT(2026, 11, 5, 5, 0), datetime.date(2026, 11, 4)),
    ],
    ids=["0459", "0500"],
)
def test_O18_D4_yesterday_rollover(now, expected):
    assert learn.parse_date("yesterday", now=now) == expected


def test_O18_D4_month_boundary():
    assert learn.parse_date("today", now=DT(2026, 3, 1, 1, 0)) == datetime.date(2026, 2, 28)
    assert learn.parse_date("yesterday", now=DT(2026, 3, 1, 6, 0)) == datetime.date(2026, 2, 28)


@pytest.mark.parametrize("value", ["2026-13-01", "2026/11/05", "x"])
def test_O18_D5_invalid_values(value):
    with pytest.raises(learn.LearnError) as ei:
        learn.parse_date(value, now=DT(2026, 11, 5, 12, 0))
    assert ei.value.code == 2
    assert value in str(ei.value)


def test_O18_parse_date_without_now_is_valid_date():
    today = datetime.date.today()
    assert 0 <= (today - learn.parse_date("today")).days <= 1
    assert 1 <= (today - learn.parse_date("yesterday")).days <= 2


@pytest.mark.parametrize(
    "argv",
    [
        ["record", "T", "--level", "1", "--evidence", "e", "--summary", "s", "--date", "x"],
        ["record", "T", "--level", "1", "--evidence", "e", "--summary", "s", "--date", "2026-13-01"],
        ["fetch", "SRC", "--date", "2026/11/05", "--slug", "s"],
    ],
    ids=["record_x", "record_month13", "fetch_slashes"],
)
def test_O18_D6_cli_invalid_date(tmp_path, capsys, argv):
    root = make_root(tmp_path)
    src = tmp_path / "src.md"
    src.write_text("# s\n", encoding="utf-8")
    argv = [str(src) if a == "SRC" else a for a in argv]
    before = snapshot(tmp_path)
    rc = run_main(learn.main, argv, {"LLM_WIKI_ROOT": str(root)}, tmp_path)
    err = capsys.readouterr().err
    assert rc == 2
    assert err.strip()
    assert snapshot(tmp_path) == before


def test_O10_M11_cli_control_char_title_escaped(tmp_path, capsys):
    root = make_root(tmp_path)
    rc = run_main(
        learn.main,
        ["record", "a\tb", "--level", "1", "--evidence", "e", "--summary", "s", "--date", DS],
        {"LLM_WIKI_ROOT": str(root)},
        tmp_path,
    )
    err = capsys.readouterr().err
    assert rc == 2
    assert "a\\tb" in err and "\t" not in err
