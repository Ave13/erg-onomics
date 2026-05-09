CSS = """
<style>
/* ── Hide Streamlit chrome ─────────────────────────────────────── */
#MainMenu, footer, header { visibility: hidden; }
.stDeployButton { display: none; }

/* ── App background ────────────────────────────────────────────── */
.stApp, html, body { background-color: #111118 !important; }

/* ── Remove max-width container ────────────────────────────────── */
.block-container {
    max-width: 100% !important;
    padding: 0.5rem 0.75rem !important;
}

/* ── Tabs ─────────────────────────────────────────────────────── */
.stTabs [data-baseweb="tab"] {
    font-size: 1.1rem !important;
    padding: 12px 18px !important;
    font-weight: 600;
    color: #9aa0c0 !important;
}
.stTabs [data-baseweb="tab"][aria-selected="true"] {
    color: #f2f2f8 !important;
}
.stTabs [data-baseweb="tab-list"] {
    background-color: #1a1b24 !important;
    border-radius: 10px;
    padding: 2px;
    gap: 2px;
}

/* ── Buttons: finger-size (60 px min) ──────────────────────────── */
.stButton > button {
    height: 60px !important;
    font-size: 1.1rem !important;
    font-weight: 700 !important;
    border-radius: 10px !important;
    border: none !important;
    background-color: #2c3044 !important;
    color: #c8ceeb !important;
    width: 100%;
    transition: opacity 0.15s;
}
.stButton > button:hover { opacity: 0.85; }
.stButton > button:disabled {
    background-color: #181921 !important;
    color: #3a3f52 !important;
}

/* Start button */
.btn-start > div > button { background-color: #1a9e5c !important; color: #fff !important; }
/* End button */
.btn-end   > div > button { background-color: #c0392b !important; color: #fff !important; }
/* Pause button */
.btn-pause > div > button { background-color: #2474b8 !important; color: #fff !important; }

/* ── Text inputs & number inputs ───────────────────────────────── */
.stTextInput input,
.stNumberInput input,
.stDateInput input {
    background-color: #1e2030 !important;
    color: #f2f2f8 !important;
    border-color: #383c4d !important;
    border-radius: 8px !important;
    font-size: 1.05rem !important;
    min-height: 48px !important;
}
label { color: #9aa0c0 !important; }

/* ── Selectbox ─────────────────────────────────────────────────── */
[data-baseweb="select"] > div {
    background-color: #1e2030 !important;
    border-color: #383c4d !important;
    border-radius: 8px !important;
    color: #f2f2f8 !important;
    min-height: 48px !important;
}

/* ── Expander ─────────────────────────────────────────────────── */
.streamlit-expanderHeader {
    background-color: #1e2030 !important;
    border-radius: 8px !important;
    color: #c8ceeb !important;
    font-size: 0.95rem !important;
}
.streamlit-expanderContent {
    background-color: #161720 !important;
    border-radius: 0 0 8px 8px !important;
}

/* ── Info / warning / success alerts ───────────────────────────── */
.stAlert { border-radius: 8px !important; }

/* ── Divider ──────────────────────────────────────────────────── */
hr { border-color: #282a3a !important; }

/* ── Subheader / caption ──────────────────────────────────────── */
h2, h3 { color: #d0d4e8 !important; }
.stCaption { color: #737aaa !important; }

/* ── Radio buttons ─────────────────────────────────────────────── */
.stRadio [data-testid="stMarkdownContainer"] { color: #c8ceeb; }
</style>
"""
