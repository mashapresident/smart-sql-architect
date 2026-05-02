"""
main.py — Точка входу Streamlit-застосунку Smart SQL Architect.

Запуск:
    streamlit run src/sql_architect/main.py
"""

from __future__ import annotations

import os

import sqlparse
import streamlit as st
from dotenv import load_dotenv
from google.api_core.exceptions import InvalidArgument, ResourceExhausted

from sql_architect.core import SQLArchitect, _schema_to_text
from sql_architect.presets import EXAMPLE_QUESTIONS, PRESET_SCHEMAS
from sql_architect.schemas import SQLQueryResult

load_dotenv()

# ──────────────────────────────────────────────────────────────────────────────
# Streamlit page config
# ──────────────────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Smart SQL Architect",
    page_icon="🗄️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ──────────────────────────────────────────────────────────────────────────────
# Custom CSS
# ──────────────────────────────────────────────────────────────────────────────

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600&family=DM+Sans:ital,wght@0,400;0,500;0,700&display=swap');

    html, body, [class*="css"] {
        font-family: 'DM Sans', sans-serif;
    }

    /* SQL code block */
    .sql-block {
        background: #0d1117;
        color: #e6edf3;
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.85rem;
        border-radius: 10px;
        padding: 1.1rem 1.3rem;
        border-left: 4px solid #388bfd;
        white-space: pre;
        overflow-x: auto;
        line-height: 1.65;
        margin: 4px 0 8px 0;
    }

    /* Complexity / table badges */
    .badge {
        display: inline-block;
        padding: 2px 11px;
        border-radius: 20px;
        font-size: 0.76rem;
        font-weight: 600;
        margin: 2px 3px 2px 0;
    }
    .badge-simple   { background: #1f6feb22; color: #58a6ff; border: 1px solid #58a6ff55; }
    .badge-moderate { background: #d29922222; color: #e3b341; border: 1px solid #e3b34155; }
    .badge-complex  { background: #f8514922; color: #f85149; border: 1px solid #f8514955; }
    .badge-table    { background: #238636222; color: #3fb950; border: 1px solid #3fb95055; }

    /* Cached indicator */
    .cached-tag {
        font-size: 0.72rem;
        color: #79c0ff;
        background: #388bfd18;
        border: 1px solid #388bfd44;
        border-radius: 6px;
        padding: 2px 8px;
        margin-left: 6px;
        vertical-align: middle;
    }

    /* Warning / alternative items */
    .warn-item { color: #e3b341; font-size: 0.88rem; margin: 3px 0; }
    .alt-item  { color: #8b949e; font-size: 0.88rem; margin: 3px 0; }

    /* Section separator */
    .sec-label {
        font-size: 0.8rem;
        font-weight: 600;
        color: #8b949e;
        letter-spacing: 0.06em;
        text-transform: uppercase;
        margin: 10px 0 4px 0;
    }

    /* Sidebar example buttons */
    div[data-testid="stSidebar"] button {
        text-align: left !important;
        font-size: 0.78rem !important;
        padding: 5px 8px !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ──────────────────────────────────────────────────────────────────────────────
# Sidebar
# ──────────────────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("## SQL Architect")
    st.caption("Natural Language → SQL")
    st.divider()

    # API key
    api_key = st.text_input(
        "Gemini API Key",
        value=os.getenv("GEMINI_API_KEY", ""),
        type="password",
        help="Отримати ключ: https://aistudio.google.com/app/apikey",
    )

    st.divider()

    # Preset selector
    preset_name = st.selectbox(
        "Схема бази даних",
        list(PRESET_SCHEMAS.keys()),
        help="Оберіть вбудовану схему або налаштуйте власну нижче",
    )

    # Cache toggle
    use_cache = st.toggle("Кешувати запити (TTL 1 год.)", value=True)

    st.divider()
    st.markdown("**Приклади запитань:**")

    for q in EXAMPLE_QUESTIONS[preset_name]:
        if st.button(q, use_container_width=True, key=f"ex_{hash(q)}"):
            st.session_state["prefill_question"] = q
            st.rerun()

    st.divider()
    st.caption(
        "Проєкт: Smart SQL Architect  \n"
        "Модель: Gemini 2.5 Flash  \n"
        "Параметри: temp=0.1 · top_p=0.85 · top_k=20"
    )

# Main content
st.title("Smart SQL Architect")
st.markdown(
    "Введіть запит природною мовою — отримайте оптимізований SQL, "
    "адаптований до вашої схеми БД."
)

# ── Question input 

prefill = st.session_state.pop("prefill_question", "")
question = st.text_area(
    "Ваш запит",
    value=prefill,
    placeholder="Наприклад: Покажи топ-5 покупців за загальними витратами за минулий місяць",
    height=90,
    label_visibility="collapsed",
)

col_gen, col_clear = st.columns([1, 5])
with col_gen:
    generate_clicked = st.button("⚡ Згенерувати", type="primary", use_container_width=True)
with col_clear:
    if st.button("Очистити результат", use_container_width=False):
        st.session_state.pop("last_result", None)
        st.session_state.pop("last_question", None)
        st.rerun()

#  Active schema preview

schema = PRESET_SCHEMAS[preset_name]

with st.expander("📐 Активна схема БД", expanded=False):
    st.code(_schema_to_text(schema), language="sql")

if generate_clicked:
    if not api_key:
        st.error("Вкажіть Gemini API Key у бічній панелі.")
        st.stop()
    if not question.strip():
        st.warning("Введіть запит перед генерацією.")
        st.stop()

    with st.spinner("Gemini генерує SQL-запит…"):
        try:
            architect = SQLArchitect(api_key=api_key, use_cache=use_cache)
            result = architect.generate_sql(question.strip(), schema)
            st.session_state["last_result"] = result
            st.session_state["last_question"] = question.strip()
            st.session_state["from_cache"] = (
                use_cache  # спрощена індикація — реальна перевірка через лог
            )
        except ResourceExhausted as exc:
            st.error(
                f"⏳ **Перевищено ліміт Gemini Free Tier.**  \n"
                f"Зачекайте ~60 сек. та спробуйте ще раз.  \n\n`{exc}`"
            )
            st.stop()
        except InvalidArgument as exc:
            st.error(f"**Невірний API-ключ або формат запиту.**  \n\n`{exc}`")
            st.stop()
        except ValueError as exc:
            st.error(
                f"**Не вдалося розібрати відповідь моделі.**  \n\n```\n{exc}\n```"
            )
            st.stop()
        except Exception as exc:  # noqa: BLE001
            st.error(f"Непередбачена помилка: `{exc}`")
            st.stop()

if "last_result" in st.session_state:
    result: SQLQueryResult = st.session_state["last_result"]
    shown_q: str = st.session_state.get("last_question", "")

    st.divider()

    # Header
    st.subheader(f'"{shown_q}"')

    # Complexity + table badges
    complexity_cls = f"badge-{result.estimated_complexity}"
    badges_html = (
        f'<span class="badge {complexity_cls}">'
        f'{result.estimated_complexity.upper()}</span>'
    )
    for t in result.tables_used:
        badges_html += f'<span class="badge badge-table">{t}</span>'

    st.markdown(badges_html, unsafe_allow_html=True)

    st.markdown("")

    # ── SQL query ──────────────────────────────────────────────────────────

    st.markdown('<div class="sec-label">Згенерований SQL</div>', unsafe_allow_html=True)

    # Форматуємо через sqlparse для гарного відступу
    try:
        formatted_sql = sqlparse.format(
            result.sql_query,
            reindent=True,
            keyword_case="upper",
            indent_width=4,
        )
    except Exception:
        formatted_sql = result.sql_query

    st.markdown(
        f'<div class="sql-block">{formatted_sql}</div>',
        unsafe_allow_html=True,
    )

    dl_col, copy_col = st.columns([2, 8])
    with dl_col:
        st.download_button(
            "Завантажити .sql",
            data=formatted_sql,
            file_name="query.sql",
            mime="text/plain",
            use_container_width=True,
        )

    # ── Explanation ────────────────────────────────────────────────────────

    st.markdown('<div class="sec-label">Пояснення</div>', unsafe_allow_html=True)
    st.info(result.explanation)

    # ── Warnings ───────────────────────────────────────────────────────────

    if result.warnings:
        st.markdown('<div class="sec-label">Попередження</div>', unsafe_allow_html=True)
        warnings_html = "".join(
            f'<div class="warn-item">• {w}</div>' for w in result.warnings
        )
        st.markdown(warnings_html, unsafe_allow_html=True)

    # ── Alternatives ───────────────────────────────────────────────────────

    if result.alternative_approaches:
        with st.expander("Альтернативні підходи"):
            alts_html = "".join(
                f'<div class="alt-item">→ {a}</div>'
                for a in result.alternative_approaches
            )
            st.markdown(alts_html, unsafe_allow_html=True)

    # ── Raw JSON ───────────────────────────────────────────────────────────

    with st.expander("Сирий JSON (структурований вивід Gemini)"):
        st.json(result.model_dump())
