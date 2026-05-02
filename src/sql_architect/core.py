"""
core.py — Основна логіка взаємодії з Gemini API.

Реалізовано:
  - system_instruction для визначення ролі моделі
  - Few-shot prompting (2 приклади) для стабільного структурованого виводу
  - Pydantic-валідація відповіді (SQLQueryResult)
  - Локальне кешування запитів через diskcache (TTL = 1 год.)
  - Обробка помилок: ResourceExhausted, InvalidArgument, ValueError
  - Обґрунтовані параметри моделі: temperature=0.1, top_p=0.85, top_k=20
"""

from __future__ import annotations

import hashlib
import json
import logging
import os

import diskcache
import google.generativeai as genai
from google.api_core.exceptions import InvalidArgument, ResourceExhausted
from pydantic import ValidationError

from .schemas import DatabaseSchema, SQLQueryResult

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Cache
# ──────────────────────────────────────────────────────────────────────────────

_CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", "..", ".query_cache")
_cache = diskcache.Cache(_CACHE_DIR)
_CACHE_TTL = 3600  # 1 година

# ──────────────────────────────────────────────────────────────────────────────
# System instruction  (виноситься в окремий параметр при створенні моделі)
# ──────────────────────────────────────────────────────────────────────────────

SYSTEM_INSTRUCTION = """
Ти — провідний SQL-архітектор з 15-річним досвідом проєктування та оптимізації
реляційних баз даних. Твоя єдина мета — перетворювати запитання природною мовою
на правильні, ефективні SQL-запити на основі наданої схеми БД.

Правила, яких ти ЗОБОВ'ЯЗАНИЙ дотримуватися:
1. Завжди уважно вивчай схему перед написанням будь-якого SQL.
2. Використовуй явний синтаксис JOIN (ніяких неявних з'єднань через кому).
3. Надавай перевагу CTE (конструкції WITH) над глибоко вкладеними підзапитами.
4. Додавай змістовні псевдоніми таблиць.
5. Поважай SQL-діалект, зазначений у схемі (за замовчуванням PostgreSQL).
6. Ніколи не вигадуй стовпці або таблиці, яких немає в схемі.
7. Завжди відповідай ТІЛЬКИ валідним JSON, що точно відповідає схемі SQLQueryResult.
8. Якщо запит неоднозначний — зроби розумні припущення і вкажи їх у warnings.
9. Жодного тексту поза JSON — ні markdown-огорток, ні пояснень до/після JSON.
""".strip()

# ──────────────────────────────────────────────────────────────────────────────
# Few-shot examples  (2 приклади для стабільного структурованого виводу)
# ──────────────────────────────────────────────────────────────────────────────

_FEW_SHOT: list[dict] = [
    # ── Приклад 1 ─────────────────────────────────────────────────────────────
    {
        "role": "user",
        "parts": [
            "Схема:\n"
            "Database: ecommerce (PostgreSQL)\n"
            "Tables:\n"
            "  customers(id SERIAL PK NOT NULL, name VARCHAR(120) NOT NULL, "
            "email VARCHAR(255) NOT NULL, created_at TIMESTAMP NOT NULL)\n"
            "  orders(id SERIAL PK NOT NULL, customer_id INTEGER NOT NULL FK→customers.id, "
            "total DECIMAL(12,2) NOT NULL, status VARCHAR(30) NOT NULL, "
            "created_at TIMESTAMP NOT NULL)\n"
            "  order_items(id SERIAL PK NOT NULL, order_id INTEGER NOT NULL FK→orders.id, "
            "product_id INTEGER NOT NULL FK→products.id, quantity INTEGER NOT NULL, "
            "unit_price DECIMAL(10,2) NOT NULL)\n"
            "  products(id SERIAL PK NOT NULL, name VARCHAR(200) NOT NULL, "
            "category VARCHAR(80), price DECIMAL(10,2) NOT NULL)\n\n"
            "Запитання: Покажи топ-5 покупців за загальними витратами за минулий місяць."
        ],
    },
    {
        "role": "model",
        "parts": [
            json.dumps(
                {
                    "sql_query": (
                        "WITH monthly_spending AS (\n"
                        "    SELECT\n"
                        "        c.id,\n"
                        "        c.name,\n"
                        "        c.email,\n"
                        "        SUM(o.total) AS total_spent\n"
                        "    FROM customers c\n"
                        "    INNER JOIN orders o ON o.customer_id = c.id\n"
                        "    WHERE o.status = 'completed'\n"
                        "      AND o.created_at >= DATE_TRUNC('month', NOW() - INTERVAL '1 month')\n"
                        "      AND o.created_at <  DATE_TRUNC('month', NOW())\n"
                        "    GROUP BY c.id, c.name, c.email\n"
                        ")\n"
                        "SELECT id, name, email, total_spent\n"
                        "FROM   monthly_spending\n"
                        "ORDER  BY total_spent DESC\n"
                        "LIMIT  5;"
                    ),
                    "explanation": (
                        "1. CTE monthly_spending агрегує загальну суму замовлень на покупця "
                        "за попередній календарний місяць через DATE_TRUNC для чітких меж місяця. "
                        "2. Враховуються лише замовлення зі статусом 'completed'. "
                        "3. Зовнішній запит сортує за total_spent DESC і повертає перші 5 рядків."
                    ),
                    "tables_used": ["customers", "orders"],
                    "estimated_complexity": "moderate",
                    "warnings": [
                        "Припускається, що 'completed' — правильний статус оплачених замовлень. Перевірте enum-значення у своїй системі.",
                        "Індекс на orders(customer_id, created_at, status) суттєво покращить продуктивність.",
                    ],
                    "alternative_approaches": [
                        "Використайте віконну функцію RANK() OVER (ORDER BY SUM(total) DESC), якщо треба коректно обробляти однакові значення.",
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
        ],
    },
    # ── Приклад 2 ─────────────────────────────────────────────────────────────
    {
        "role": "user",
        "parts": [
            "Схема:\n"
            "Database: hr_system (PostgreSQL)\n"
            "Tables:\n"
            "  employees(id SERIAL PK NOT NULL, name VARCHAR(120) NOT NULL, "
            "department_id INTEGER FK→departments.id, salary DECIMAL(10,2) NOT NULL, "
            "hire_date DATE NOT NULL)\n"
            "  departments(id SERIAL PK NOT NULL, name VARCHAR(100) NOT NULL, "
            "manager_id INTEGER FK→employees.id)\n\n"
            "Запитання: Знайди всіх працівників, прийнятих за останній рік, "
            "чия зарплата перевищує середню зарплату по їхньому відділу."
        ],
    },
    {
        "role": "model",
        "parts": [
            json.dumps(
                {
                    "sql_query": (
                        "WITH dept_avg AS (\n"
                        "    SELECT department_id,\n"
                        "           AVG(salary) AS avg_salary\n"
                        "    FROM   employees\n"
                        "    GROUP  BY department_id\n"
                        ")\n"
                        "SELECT\n"
                        "    e.id,\n"
                        "    e.name,\n"
                        "    d.name        AS department,\n"
                        "    e.salary,\n"
                        "    da.avg_salary AS dept_avg_salary,\n"
                        "    e.hire_date\n"
                        "FROM  employees   e\n"
                        "INNER JOIN departments d  ON d.id  = e.department_id\n"
                        "INNER JOIN dept_avg    da ON da.department_id = e.department_id\n"
                        "WHERE e.hire_date >= CURRENT_DATE - INTERVAL '1 year'\n"
                        "  AND e.salary    >  da.avg_salary\n"
                        "ORDER BY e.hire_date DESC;"
                    ),
                    "explanation": (
                        "1. CTE dept_avg обчислює середню зарплату по кожному відділу для всіх "
                        "працівників (не лише нових) — це стандартна бізнес-інтерпретація. "
                        "2. Основний запит з'єднує employees з departments (для назв) і з dept_avg. "
                        "3. Два умови WHERE: прийнятий за останні 365 днів, і зарплата вище середньої по відділу."
                    ),
                    "tables_used": ["employees", "departments"],
                    "estimated_complexity": "moderate",
                    "warnings": [
                        "dept_avg розраховується по ВСІХ працівниках, а не лише по новим — це типова бізнес-інтерпретація.",
                    ],
                    "alternative_approaches": [
                        "Замініть CTE корельованим підзапитом у WHERE (менш читабельно, але уникає JOIN).",
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
        ],
    },
]


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────


def _schema_to_text(schema: DatabaseSchema) -> str:
    """Серіалізує DatabaseSchema у читабельний текстовий рядок для промпту."""
    lines = [f"Database: {schema.database_name} ({schema.dialect})", "Tables:"]
    for table in schema.tables:
        col_parts: list[str] = []
        for col in table.columns:
            flags: list[str] = []
            if col.primary_key:
                flags.append("PK")
            if col.foreign_key:
                flags.append(f"FK→{col.foreign_key}")
            if not col.nullable:
                flags.append("NOT NULL")
            flag_str = " " + " ".join(flags) if flags else ""
            col_parts.append(f"{col.name} {col.data_type}{flag_str}")
        cols = ", ".join(col_parts)
        desc = f"  -- {table.description}" if table.description else ""
        lines.append(f"  {table.name}({cols}){desc}")
    return "\n".join(lines)


def _schema_hash(schema: DatabaseSchema) -> str:
    return hashlib.md5(schema.model_dump_json().encode()).hexdigest()


def _cache_key(natural_language: str, schema_hash: str) -> str:
    combined = f"{natural_language.strip().lower()}|{schema_hash}"
    return hashlib.sha256(combined.encode()).hexdigest()


def _strip_markdown_fences(text: str) -> str:
    """Видаляє markdown-огортки ```json … ``` якщо модель їх додала."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        lines = lines[1:]  # прибрати рядок з ```
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text


# ──────────────────────────────────────────────────────────────────────────────
# Main class
# ──────────────────────────────────────────────────────────────────────────────


class SQLArchitect:
    """
    Клієнт Gemini API для перетворення природної мови на SQL.

    Parameters
    ----------
    api_key : str
        Ключ Gemini API.
    use_cache : bool
        Якщо True, успішні результати зберігаються на диску та повертаються
        при повторних ідентичних запитах (TTL = 1 год.).
    """

    MODEL_NAME = "gemini-2.5-flash"

    def __init__(self, api_key: str, use_cache: bool = True) -> None:
        genai.configure(api_key=api_key)
        self._use_cache = use_cache

        # system_instruction виноситься в окремий параметр — вимога ТЗ п. 3c
        self._model = genai.GenerativeModel(
            model_name=self.MODEL_NAME,
            system_instruction=SYSTEM_INSTRUCTION,
            generation_config=genai.GenerationConfig(
                # temperature=0.1 — SQL має бути коректним, а не творчим;
                # майже детермінований вивід
                temperature=0.1,
                # top_p=0.85 — трохи обмежує nucleus-sampling для стабільності
                top_p=0.85,
                # top_k=20 — не дозволяє проникати малоймовірним токенам
                top_k=20,
                # 2048 токенів — достатньо для будь-якого запиту + JSON-обгортки
                max_output_tokens=2048,
            ),
        )
        logger.info("SQLArchitect ініціалізовано (модель: %s)", self.MODEL_NAME)

    # ── Public API ────────────────────────────────────────────────────────────

    def generate_sql(
        self,
        natural_language: str,
        schema: DatabaseSchema,
    ) -> SQLQueryResult:
        """
        Перетворює запит природною мовою на SQL-запит.

        Parameters
        ----------
        natural_language : str
            Запит користувача.
        schema : DatabaseSchema
            Схема БД, на основі якої генерується SQL.

        Returns
        -------
        SQLQueryResult
            Валідований Pydantic-об'єкт з SQL-запитом та метаданими.

        Raises
        ------
        ResourceExhausted
            Перевищено ліміт Free Tier Gemini API.
        InvalidArgument
            Невірний ключ API або формат запиту.
        ValueError
            Модель повернула не-JSON або структура не відповідає SQLQueryResult.
        """
        s_hash = _schema_hash(schema)

        # ── Перевірка кешу ────────────────────────────────────────────────────
        if self._use_cache:
            key = _cache_key(natural_language, s_hash)
            try:
                cached_raw = _cache.get(key)
                if cached_raw is not None:
                    logger.info("Cache hit: %s…", natural_language[:60])
                    return SQLQueryResult.model_validate(json.loads(cached_raw))
            except Exception as exc:  # pragma: no cover
                logger.warning("Помилка читання кешу (ігноруємо): %s", exc)

        # ── Виклик Gemini API ─────────────────────────────────────────────────
        prompt = self._build_prompt(natural_language, schema)

        try:
            chat = self._model.start_chat(history=_FEW_SHOT)
            response = chat.send_message(prompt)
        except ResourceExhausted as exc:
            logger.error("ResourceExhausted: %s", exc)
            raise ResourceExhausted(
                "Перевищено ліміт Gemini Free Tier. "
                "Зачекайте хвилину та спробуйте ще раз."
            ) from exc
        except InvalidArgument as exc:
            logger.error("InvalidArgument: %s", exc)
            raise InvalidArgument(
                f"Невірний API-ключ або формат запиту: {exc}"
            ) from exc

        # ── Парсинг відповіді ─────────────────────────────────────────────────
        result = self._parse_response(response.text)
        logger.info(
            "SQL згенеровано (складність: %s, таблиці: %s)",
            result.estimated_complexity,
            result.tables_used,
        )

        # ── Збереження у кеш ──────────────────────────────────────────────────
        if self._use_cache:
            try:
                _cache.set(key, result.model_dump_json(), expire=_CACHE_TTL)
            except Exception as exc:  # pragma: no cover
                logger.warning("Помилка запису кешу (ігноруємо): %s", exc)

        return result

    # ── Private helpers ───────────────────────────────────────────────────────

    def _build_prompt(self, question: str, schema: DatabaseSchema) -> str:
        schema_text = _schema_to_text(schema)
        return f"Схема:\n{schema_text}\n\nЗапитання: {question}"

    @staticmethod
    def _parse_response(raw: str) -> SQLQueryResult:
        """
        Парсить JSON-відповідь моделі у SQLQueryResult.

        Обробляє випадки, коли модель загортає JSON у markdown-фенси.
        """
        text = _strip_markdown_fences(raw)

        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Модель повернула не-JSON відповідь.\n"
                f"Сирий вивід:\n{raw}\n\nПомилка: {exc}"
            ) from exc

        try:
            return SQLQueryResult.model_validate(data)
        except ValidationError as exc:
            raise ValueError(
                f"Відповідь моделі не відповідає схемі SQLQueryResult.\n{exc}"
            ) from exc
