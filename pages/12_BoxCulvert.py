# pages/12_BoxCulvert.py

import streamlit as st
from boxculvert.lang_dict import lang_dict
from boxculvert.ui_input import input_page
from boxculvert.ui_calculation import calculation_page
from boxculvert.ui_output import output_page

st.set_page_config(page_title="Box Culvert Design", layout="wide")

def t(key):
    return lang_dict[st.session_state.get("lang", "EN")].get(key, key)

# --- language & navigation ---
if "lang" not in st.session_state:
    st.session_state.lang = "EN"
if "page" not in st.session_state:
    st.session_state.page = "input"

st.sidebar.title(t("language_select"))
lang = st.sidebar.selectbox("Language", ["EN", "IN"],
                            index=0 if st.session_state.lang == "EN" else 1)
st.session_state.lang = lang

st.sidebar.title(t("navigation"))
page = st.sidebar.radio("Go to", ["input", "calculation", "output"],
                        format_func=lambda p: t(f"{p}_page"),
                        index=["input","calculation","output"].index(st.session_state.page))
st.session_state.page = page

# Route
if st.session_state.page == "input":
    input_page()
elif st.session_state.page == "calculation":
    calculation_page()
elif st.session_state.page == "output":
    output_page()
