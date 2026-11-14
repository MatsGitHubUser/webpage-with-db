"""End-to-end tests of the Streamlit page, run against a real Postgres."""

from conftest import APP_DIR
from streamlit.testing.v1 import AppTest

import db

APP = str(APP_DIR / "app.py")


def visit():
    at = AppTest.from_file(APP, default_timeout=30)
    at.run()
    return at


def click(at, label):
    next(b for b in at.button if b.label == label).click().run()


def give_name(at, name):
    at.text_input[0].input(name)
    click(at, "Continue")


def markdown_texts(at):
    return [m.value for m in at.markdown]


def test_visitor_is_asked_for_name_first():
    at = visit()
    assert not at.exception
    assert at.text_input[0].label == "What is your name?"
    assert len(at.text_area) == 0


def test_blank_name_is_rejected():
    at = visit()
    give_name(at, "   ")
    assert at.error[0].value == "Name cannot be empty."
    assert at.text_input[0].label == "What is your name?"


def test_comment_is_saved_and_seen_by_next_visitor(pool):
    at = visit()
    give_name(at, "Ann")
    assert "Commenting as **Ann**" in markdown_texts(at)

    at.text_area[0].input("Hello there")
    click(at, "Post comment")
    assert not at.exception
    assert [(c.author, c.body) for c in db.list_comments(pool)] == [("Ann", "Hello there")]

    other = visit()
    give_name(other, "Bob")
    assert "Hello there" in markdown_texts(other)
    assert any(t.startswith("**Ann** · ") for t in markdown_texts(other))


def test_comment_text_is_not_formatted():
    at = visit()
    give_name(at, "Ann")
    at.text_area[0].input("**bold** [link](http://example.com)")
    click(at, "Post comment")
    assert r"\*\*bold\*\* \[link\]\(http://example\.com\)" in markdown_texts(at)


def test_change_name_asks_again():
    at = visit()
    give_name(at, "Ann")
    click(at, "Change name")
    assert at.text_input[0].label == "What is your name?"
