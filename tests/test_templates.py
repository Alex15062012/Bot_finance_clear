from app.services.templates import render_template


def test_render_name():
    assert render_template("{{name}}, здравствуйте!", {"name": "Анна"}) == "Анна, здравствуйте!"


def test_render_missing_var_empty():
    assert render_template("Hi {{name}}!", {}) == "Hi !"


def test_render_spaces_in_braces():
    assert render_template("{{ name }}", {"name": "X"}) == "X"
