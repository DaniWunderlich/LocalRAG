"""Shared application shell with a conversation-first information architecture."""

import streamlit as st

from ui import apply_design
from workspace import render

st.set_page_config(
    page_title="Local RAG",
    page_icon=":material/book_2:",
    layout="wide",
    initial_sidebar_state="auto",
)
apply_design()
page = st.navigation(
    [
        st.Page(render, title="Chats", icon=":material/chat_bubble:", default=True),
        st.Page("pages/1_Documents.py", title="Library", icon=":material/folder_open:"),
        st.Page("pages/2_Settings.py", title="Settings", icon=":material/tune:"),
    ],
    position="top",
)
page.run()
