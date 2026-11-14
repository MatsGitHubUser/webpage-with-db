"""Comment wall: visitors give their name, then read and post comments."""

import re
from datetime import timezone

import psycopg
import psycopg_pool
import streamlit as st

import db

st.set_page_config(page_title="Comments", page_icon="💬")

_MARKDOWN_SPECIAL = re.compile(r"([\\`*_{}\[\]()#+\-.!|<>~$])")


def as_plain_markdown(text: str) -> str:
    """Escape user text so it is shown as typed, not formatted as Markdown."""
    return _MARKDOWN_SPECIAL.sub(r"\\\1", text).replace("\n", "  \n")


@st.cache_resource
def get_pool():
    return db.open_pool()


def ask_for_name():
    st.title("Welcome!")
    with st.form("name_form"):
        name = st.text_input("What is your name?", max_chars=db.MAX_NAME)
        submitted = st.form_submit_button("Continue")
    if submitted:
        try:
            st.session_state.visitor_name = db.clean(name, db.MAX_NAME, "Name")
        except ValueError as err:
            st.error(str(err))
        else:
            st.rerun()


def comment_page(name: str):
    st.title("Comments")
    left, right = st.columns([3, 1], vertical_alignment="center")
    left.markdown(f"Commenting as **{as_plain_markdown(name)}**")
    if right.button("Change name"):
        del st.session_state.visitor_name
        st.rerun()

    with st.form("comment_form", clear_on_submit=True):
        body = st.text_area("Write a comment", max_chars=db.MAX_BODY)
        posted = st.form_submit_button("Post comment")

    try:
        pool = get_pool()
        if posted:
            try:
                db.add_comment(pool, name, body)
            except ValueError as err:
                st.error(str(err))
            else:
                st.toast("Comment saved")
        comments = db.list_comments(pool)
    except (psycopg.OperationalError, psycopg_pool.PoolTimeout):
        st.error("The database can't be reached right now. Please try again in a minute.")
        st.stop()

    heading, refresh = st.columns([3, 1], vertical_alignment="center")
    heading.subheader("Latest comments")
    refresh.button("Refresh")
    if not comments:
        st.info("No comments yet. Be the first to write one!")
    for comment in comments:
        written = comment.created_at.astimezone(timezone.utc)
        with st.container(border=True):
            st.markdown(f"**{as_plain_markdown(comment.author)}** · {written:%Y-%m-%d %H:%M} UTC")
            st.markdown(as_plain_markdown(comment.body))


name = st.session_state.get("visitor_name")
if name:
    comment_page(name)
else:
    ask_for_name()
