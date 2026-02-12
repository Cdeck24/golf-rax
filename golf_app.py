import streamlit as st
import streamlit.components.v1 as components

# Configure the Streamlit page to use the full width
st.set_page_config(layout="wide", page_title="Golf OTD Tracker")

# Hide the default Streamlit header/menu to make it look like a native app
hide_st_style = """
            <style>
            #MainMenu {visibility: hidden;}
            footer {visibility: hidden;}
            header {visibility: hidden;}
            </style>
            """
st.markdown(hide_st_style, unsafe_allow_html=True)

# Read the HTML file from your directory
with open("index.html", "r", encoding="utf-8") as f:
    html_data = f.read()

# Render the HTML inside Streamlit
# Adjust the height depending on how large you want the window
components.html(html_data, height=900, scrolling=True)
