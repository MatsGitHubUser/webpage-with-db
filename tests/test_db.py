import pytest

import db


def test_clean_trims_and_removes_nul():
    assert db.clean("  Ann\x00 ", 10, "Name") == "Ann"


@pytest.mark.parametrize("value", ["", "   ", None])
def test_clean_rejects_empty(value):
    with pytest.raises(ValueError, match="Name cannot be empty"):
        db.clean(value, 10, "Name")


def test_clean_rejects_too_long():
    with pytest.raises(ValueError, match="at most 3 characters"):
        db.clean("abcd", 3, "Comment")


def test_comments_are_listed_newest_first(pool):
    db.add_comment(pool, "Ann", "first")
    db.add_comment(pool, "Bob", "second")
    assert [(c.author, c.body) for c in db.list_comments(pool)] == [
        ("Bob", "second"),
        ("Ann", "first"),
    ]


def test_add_comment_validates(pool):
    with pytest.raises(ValueError, match="Comment cannot be empty"):
        db.add_comment(pool, "Ann", "  ")
    assert db.list_comments(pool) == []
