"""
schemas.py — Pydantic-моделі для структурованого виводу з Gemini API.

Кожна модель описує частину схеми бази даних або результат генерації SQL-запиту.
Pydantic автоматично валідує JSON-відповідь моделі та перетворює її на Python-об'єкти.
"""

from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field


# ──────────────────────────────────────────────────────────────────────────────
# Database schema models (вхідні дані для моделі)
# ──────────────────────────────────────────────────────────────────────────────


class SQLColumn(BaseModel):
    """Один стовпець таблиці бази даних."""

    name: str = Field(..., description="Назва стовпця")
    data_type: str = Field(..., description="SQL-тип даних, напр. INTEGER, VARCHAR(255), TIMESTAMP")
    nullable: bool = Field(default=True, description="Чи може стовпець містити NULL")
    primary_key: bool = Field(default=False, description="Чи є стовпець первинним ключем")
    foreign_key: Optional[str] = Field(
        default=None,
        description="Посилання зовнішнього ключа у форматі 'таблиця.стовпець', або None",
    )
    description: Optional[str] = Field(
        default=None,
        description="Опис стовпця для людини",
    )


class SQLTable(BaseModel):
    """Одна таблиця бази даних."""

    name: str = Field(..., description="Назва таблиці")
    columns: list[SQLColumn] = Field(..., description="Список стовпців таблиці")
    description: Optional[str] = Field(
        default=None,
        description="Опис таблиці для людини",
    )


class DatabaseSchema(BaseModel):
    """Повна схема бази даних, яка передається моделі."""

    database_name: str = Field(..., description="Назва бази даних")
    tables: list[SQLTable] = Field(..., description="Список таблиць")
    dialect: str = Field(
        default="PostgreSQL",
        description="SQL-діалект: PostgreSQL, MySQL, SQLite тощо",
    )


# ──────────────────────────────────────────────────────────────────────────────
# Output models (структурований вивід Gemini)
# ──────────────────────────────────────────────────────────────────────────────


class SQLQueryResult(BaseModel):
    """
    Структурований результат генерації SQL-запиту.

    Gemini повертає JSON, що відповідає цій схемі.
    Pydantic валідує відповідь і перетворює її на об'єкт Python.
    """

    sql_query: str = Field(..., description="Згенерований SQL-запит")
    explanation: str = Field(
        ...,
        description="Покроковий опис того, що робить запит",
    )
    tables_used: list[str] = Field(
        ...,
        description="Назви таблиць, використаних у запиті",
    )
    estimated_complexity: str = Field(
        ...,
        description="Складність запиту: 'simple', 'moderate' або 'complex'",
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Потенційні проблеми: відсутні індекси, повне сканування тощо",
    )
    alternative_approaches: Optional[list[str]] = Field(
        default=None,
        description="Альтернативні підходи для отримання того самого результату",
    )


# ──────────────────────────────────────────────────────────────────────────────
# Cache model
# ──────────────────────────────────────────────────────────────────────────────


class CachedQuery(BaseModel):
    """Кешований результат запиту, збережений на диску."""

    natural_language: str
    schema_hash: str
    result: SQLQueryResult
    created_at: str
