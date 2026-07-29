from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest


def button_with_label(app: AppTest, text: str):
    return next(button for button in app.button if text in button.label)


def test_preview_ui_completes_adaptive_learning_loop(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LEO_DB_PATH", str(tmp_path / "ui-test.db"))
    app = AppTest.from_file(Path(__file__).parents[1] / "app.py").run(timeout=30)

    app.text_input[0].set_value("Asif")
    app.text_input[1].set_value("Python recursion")
    app.text_area[0].set_value("Trace recursive functions confidently")
    app.toggle[0].set_value(True)
    button_with_label(app, "Build my learning path").click()
    app.run(timeout=30)

    assert not app.exception
    button_with_label(app, "ready for the quiz").click()
    app.run(timeout=30)

    # Deliberately weak answers must trigger the Evaluator -> Coordinator -> Explainer loop.
    app.radio[0].set_value("It removes the need to understand the problem")
    app.text_area[0].set_value("I do not know")
    app.text_area[1].set_value("No example")
    app.radio[1].set_value("True")
    button_with_label(app, "Submit answers").click()
    app.run(timeout=30)

    assert not app.exception
    assert any("targeted" in button.label.lower() for button in app.button)
    button_with_label(app, "targeted follow-up").click()
    app.run(timeout=30)

    answer = "This answer explains the idea, why it matters, and checks a meaningful assumption."
    for text_area in app.text_area:
        text_area.set_value(answer)
    button_with_label(app, "Submit answers").click()
    app.run(timeout=30)

    assert not app.exception
    assert any("Start another topic" in button.label for button in app.button)

