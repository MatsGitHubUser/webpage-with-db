"""Così fan tutte page: the opening of the listening guide, then a comment wall
where visitors give their name and read and post comments."""

import re
from datetime import timezone
from pathlib import Path

import streamlit as st
from azure.core.exceptions import AzureError

import db

st.set_page_config(page_title="Così fan tutte", page_icon="🎭")

GUIDE_URL = "https://docs.google.com/document/d/1RvUglY0pjFoPL7NFRSsJ0aBISHK_ACKhrfgNuhh0-m8/edit"
POSTER = Path(__file__).parent / "assets" / "cosi-fan-tutte.png"

# Copied from the first page of the Google Doc at GUIDE_URL.
ABOUT = """\
Vi ser Mozarts *Così fan tutte* på Kungliga Operans stora scen fredag 20 november.
Den sjungs på italienska med svensk text på textmaskin och tar cirka 3 timmar och
20 minuter: akt 1 (85 min), 30 minuters paus, akt 2 (85 min).
[Källa: Operan](https://www.operan.se/forestallningar/cosi-fan-tutte)
"""

DETAILS = """\
**Musik:** Wolfgang Amadeus Mozart, 1790. **Libretto:** Lorenzo da Ponte (samma
team som *Figaros bröllop* och *Don Giovanni*).

**Titeln** betyder ungefär "Så gör alla kvinnor" – alltså att alla är otrogna.

**Den här uppsättningen:** Regissören Clara Svärd flyttar handlingen till
1960-talet. Den cyniske Don Alfonso är här en karismatisk konstnär som iscensätter
ett filosofiskt och psykologiskt experiment i sin ateljé. Dirigent är Alan Gilbert
eller André Callegaro – Operans sida säger inte vem som dirigerar den 20 november.

**Tips:** Lyssna på texten, inte bara musiken. Mozart låter ofta musiken vara
uppriktigare än det rollerna säger – en fejkad känsla kan plötsligt låta helt äkta.

**YouTube:** [60 s om vad operan handlar](https://www.youtube.com/shorts/9tiftvSGBSc)

**Middag innan:** [Ricardi](https://cdn.sanity.io/files/nhgo7gn1/production/85c90540798eecd768cad880d56a8b13dee5cc33.pdf)
→ [Google Maps](https://maps.google.com/maps?channel=fs&client=ubuntu-sn&udm&fvr=1&pvq=Cg0vZy8xMW5nMGhnczg1&vet=10CAAQoqAOahcKEwj4nYO8sIeYAxUAAAAAHQAAAAAQCg..i&cs=0&um=1&ie=UTF-8&fb=1&gl=se&sa=X&ftid=0x465f9d88de76e157:0xa6cae6aa526a80e6)
"""

_MARKDOWN_SPECIAL = re.compile(r"([\\`*_{}\[\]()#+\-.!|<>~$])")


def as_plain_markdown(text: str) -> str:
    """Escape user text so it is shown as typed, not formatted as Markdown."""
    return _MARKDOWN_SPECIAL.sub(r"\\\1", text).replace("\n", "  \n")


@st.cache_resource
def get_table():
    return db.open_table()


def show_guide():
    st.title("Così fan tutte – *Du tror att du känner din partner. Tänk igen…*")
    st.header("Om föreställningen")
    st.markdown(ABOUT)
    st.image(str(POSTER), width="stretch")
    st.markdown(DETAILS)
    st.markdown(f"📄 [Läs hela lyssningsguiden i Google Docs]({GUIDE_URL})")
    st.divider()


def ask_for_name():
    st.header("Comments")
    with st.form("name_form"):
        name = st.text_input("Vad heter du?", max_chars=db.MAX_NAME)
        submitted = st.form_submit_button("Continue")
    if submitted:
        try:
            st.session_state.visitor_name = db.clean(name, db.MAX_NAME, "Name")
        except ValueError as err:
            st.error(str(err))
        else:
            st.rerun()


def comment_page(name: str):
    st.header("Comments")
    left, right = st.columns([3, 1], vertical_alignment="center")
    left.markdown(f"Commenting as **{as_plain_markdown(name)}**")
    if right.button("Change name"):
        del st.session_state.visitor_name
        st.rerun()

    with st.form("comment_form", clear_on_submit=True):
        body = st.text_area("Write a comment", max_chars=db.MAX_BODY)
        posted = st.form_submit_button("Post comment")

    try:
        table = get_table()
        if posted:
            try:
                db.add_comment(table, name, body)
            except ValueError as err:
                st.error(str(err))
            else:
                st.toast("Comment saved")
        comments = db.list_comments(table)
    except AzureError:
        st.error("The comment storage can't be reached right now. Please try again in a minute.")
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


show_guide()
name = st.session_state.get("visitor_name")
if name:
    comment_page(name)
else:
    ask_for_name()
