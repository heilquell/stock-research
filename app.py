"""Multi-Page Entry-Point: ueberschreibt die file-based Sidebar-Navigation
mit st.navigation, damit der Home-Eintrag nicht mehr „main" heisst und
mit Icon + groesserer Schrift erscheint.
"""
import streamlit as st

st.markdown(
    """
    <style>
    /* Groessere Schrift fuer die Sidebar-Navigation */
    section[data-testid="stSidebar"] [data-testid="stSidebarNav"] a,
    section[data-testid="stSidebar"] [data-testid="stSidebarNavLink"],
    section[data-testid="stSidebar"] [data-testid="stSidebarNav"] a span,
    section[data-testid="stSidebar"] [data-testid="stSidebarNavLink"] span {
        font-size: 1.15rem !important;
        font-weight: 500 !important;
    }
    section[data-testid="stSidebar"] [data-testid="stSidebarNav"] a,
    section[data-testid="stSidebar"] [data-testid="stSidebarNavLink"] {
        padding: 0.5rem 0.75rem !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

pages = [
    st.Page("main.py", title="Home", icon="🏠", default=True),
    st.Page("pages/1_📊_Crossover.py", title="Crossover", icon="📊"),
    st.Page("pages/2_🧮_Optionen.py", title="Optionen", icon="🧮"),
]
pg = st.navigation(pages)
pg.run()
