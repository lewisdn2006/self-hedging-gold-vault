import os

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest

APP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "goldvault", "app.py")


def test_app_runs_and_buttons_work():
    at = AppTest.from_file(APP, default_timeout=60).run()
    assert not at.exception
    assert any("Gold price" in m.label for m in at.metric)
    labels = [b.label for b in at.button]
    assert "Run hedge rule now" in labels and "Run backtest" in labels
    next(b for b in at.button if b.label == "Run hedge rule now").click()
    at.run()
    assert not at.exception
    next(b for b in at.button if b.label == "Step one bar").click()
    at.run()
    assert not at.exception
    assert "Bar 2 of 251" in " ".join(c.value for c in at.caption)


def test_backtest_button():
    at = AppTest.from_file(APP, default_timeout=120).run()
    at.number_input[0].set_value(200)
    next(b for b in at.button if b.label == "Run backtest").click()
    at.run()
    assert not at.exception
    assert any(m.label == "Final value (hedged)" for m in at.metric)
