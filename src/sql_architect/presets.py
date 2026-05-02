"""
presets.py — Вбудовані схеми БД та приклади запитань для Streamlit UI.
"""

from __future__ import annotations

from .schemas import DatabaseSchema, SQLTable, SQLColumn

# ──────────────────────────────────────────────────────────────────────────────
# Preset schemas
# ──────────────────────────────────────────────────────────────────────────────

PRESET_SCHEMAS: dict[str, DatabaseSchema] = {
    "🛒 E-Commerce": DatabaseSchema(
        database_name="ecommerce",
        dialect="PostgreSQL",
        tables=[
            SQLTable(
                name="customers",
                description="Зареєстровані покупці",
                columns=[
                    SQLColumn(name="id", data_type="SERIAL", primary_key=True, nullable=False),
                    SQLColumn(name="name", data_type="VARCHAR(120)", nullable=False),
                    SQLColumn(name="email", data_type="VARCHAR(255)", nullable=False),
                    SQLColumn(name="country", data_type="VARCHAR(60)"),
                    SQLColumn(name="created_at", data_type="TIMESTAMP", nullable=False),
                ],
            ),
            SQLTable(
                name="products",
                description="Каталог товарів",
                columns=[
                    SQLColumn(name="id", data_type="SERIAL", primary_key=True, nullable=False),
                    SQLColumn(name="name", data_type="VARCHAR(200)", nullable=False),
                    SQLColumn(name="category", data_type="VARCHAR(80)"),
                    SQLColumn(name="price", data_type="DECIMAL(10,2)", nullable=False),
                    SQLColumn(name="stock_qty", data_type="INTEGER", nullable=False),
                ],
            ),
            SQLTable(
                name="orders",
                description="Замовлення",
                columns=[
                    SQLColumn(name="id", data_type="SERIAL", primary_key=True, nullable=False),
                    SQLColumn(name="customer_id", data_type="INTEGER", nullable=False, foreign_key="customers.id"),
                    SQLColumn(name="status", data_type="VARCHAR(30)", nullable=False, description="pending|completed|cancelled"),
                    SQLColumn(name="total", data_type="DECIMAL(12,2)", nullable=False),
                    SQLColumn(name="created_at", data_type="TIMESTAMP", nullable=False),
                ],
            ),
            SQLTable(
                name="order_items",
                columns=[
                    SQLColumn(name="id", data_type="SERIAL", primary_key=True, nullable=False),
                    SQLColumn(name="order_id", data_type="INTEGER", nullable=False, foreign_key="orders.id"),
                    SQLColumn(name="product_id", data_type="INTEGER", nullable=False, foreign_key="products.id"),
                    SQLColumn(name="quantity", data_type="INTEGER", nullable=False),
                    SQLColumn(name="unit_price", data_type="DECIMAL(10,2)", nullable=False),
                ],
            ),
        ],
    ),
    "👥 HR System": DatabaseSchema(
        database_name="hr_system",
        dialect="PostgreSQL",
        tables=[
            SQLTable(
                name="departments",
                columns=[
                    SQLColumn(name="id", data_type="SERIAL", primary_key=True, nullable=False),
                    SQLColumn(name="name", data_type="VARCHAR(100)", nullable=False),
                    SQLColumn(name="budget", data_type="DECIMAL(14,2)"),
                    SQLColumn(name="manager_id", data_type="INTEGER", foreign_key="employees.id"),
                ],
            ),
            SQLTable(
                name="employees",
                columns=[
                    SQLColumn(name="id", data_type="SERIAL", primary_key=True, nullable=False),
                    SQLColumn(name="name", data_type="VARCHAR(120)", nullable=False),
                    SQLColumn(name="email", data_type="VARCHAR(255)", nullable=False),
                    SQLColumn(name="department_id", data_type="INTEGER", foreign_key="departments.id"),
                    SQLColumn(name="salary", data_type="DECIMAL(10,2)", nullable=False),
                    SQLColumn(name="hire_date", data_type="DATE", nullable=False),
                    SQLColumn(name="job_title", data_type="VARCHAR(100)"),
                ],
            ),
            SQLTable(
                name="performance_reviews",
                columns=[
                    SQLColumn(name="id", data_type="SERIAL", primary_key=True, nullable=False),
                    SQLColumn(name="employee_id", data_type="INTEGER", nullable=False, foreign_key="employees.id"),
                    SQLColumn(name="reviewer_id", data_type="INTEGER", foreign_key="employees.id"),
                    SQLColumn(name="score", data_type="SMALLINT", nullable=False, description="Рейтинг 1–5"),
                    SQLColumn(name="review_date", data_type="DATE", nullable=False),
                    SQLColumn(name="notes", data_type="TEXT"),
                ],
            ),
        ],
    ),
    "📝 Blog / CMS": DatabaseSchema(
        database_name="blog_cms",
        dialect="PostgreSQL",
        tables=[
            SQLTable(
                name="users",
                columns=[
                    SQLColumn(name="id", data_type="SERIAL", primary_key=True, nullable=False),
                    SQLColumn(name="username", data_type="VARCHAR(60)", nullable=False),
                    SQLColumn(name="email", data_type="VARCHAR(255)", nullable=False),
                    SQLColumn(name="role", data_type="VARCHAR(20)", nullable=False, description="admin|editor|reader"),
                    SQLColumn(name="created_at", data_type="TIMESTAMP", nullable=False),
                ],
            ),
            SQLTable(
                name="posts",
                columns=[
                    SQLColumn(name="id", data_type="SERIAL", primary_key=True, nullable=False),
                    SQLColumn(name="title", data_type="VARCHAR(300)", nullable=False),
                    SQLColumn(name="author_id", data_type="INTEGER", nullable=False, foreign_key="users.id"),
                    SQLColumn(name="status", data_type="VARCHAR(20)", description="draft|published|archived"),
                    SQLColumn(name="published_at", data_type="TIMESTAMP"),
                    SQLColumn(name="views", data_type="INTEGER", nullable=False),
                ],
            ),
            SQLTable(
                name="tags",
                columns=[
                    SQLColumn(name="id", data_type="SERIAL", primary_key=True, nullable=False),
                    SQLColumn(name="name", data_type="VARCHAR(60)", nullable=False),
                ],
            ),
            SQLTable(
                name="post_tags",
                columns=[
                    SQLColumn(name="post_id", data_type="INTEGER", nullable=False, foreign_key="posts.id"),
                    SQLColumn(name="tag_id", data_type="INTEGER", nullable=False, foreign_key="tags.id"),
                ],
            ),
            SQLTable(
                name="comments",
                columns=[
                    SQLColumn(name="id", data_type="SERIAL", primary_key=True, nullable=False),
                    SQLColumn(name="post_id", data_type="INTEGER", nullable=False, foreign_key="posts.id"),
                    SQLColumn(name="user_id", data_type="INTEGER", foreign_key="users.id"),
                    SQLColumn(name="body", data_type="TEXT", nullable=False),
                    SQLColumn(name="created_at", data_type="TIMESTAMP", nullable=False),
                ],
            ),
        ],
    ),
}

# ──────────────────────────────────────────────────────────────────────────────
# Example questions per preset
# ──────────────────────────────────────────────────────────────────────────────

EXAMPLE_QUESTIONS: dict[str, list[str]] = {
    "🛒 E-Commerce": [
        "Покажи топ-5 покупців за загальними витратами за минулий місяць",
        "Знайди товари з малим запасом (менше 10 одиниць) та згрупуй по категоріях",
        "Яка середня сума замовлення по країнах у Q4 минулого року?",
        "Список всіх замовлень у статусі pending, зроблених сьогодні",
        "Які категорії товарів принесли найбільший дохід за останні 30 днів?",
    ],
    "👥 HR System": [
        "Знайди працівників, прийнятих за останній рік, із зарплатою вище середньої по відділу",
        "Який відділ має найвищий середній бал performance review цього року?",
        "Топ-3 найвищооплачуваних працівника у кожному відділі",
        "Покажи всіх працівників, які ніколи не отримували performance review",
        "Скільки працівників у кожному відділі та яка їхня середня зарплата?",
    ],
    "📝 Blog / CMS": [
        "Знайди 10 найпопулярніших опублікованих постів за останні 30 днів",
        "Які автори опублікували більше 5 постів, але не отримали жодного коментаря?",
        "Покажи всі пости, теговані одночасно 'python' та 'tutorial'",
        "Список тегів, відсортованих за кількістю опублікованих постів",
        "Скільки коментарів отримав кожен автор за весь час?",
    ],
}
