from datetime import date
from decimal import Decimal

import psycopg

from app import config


def owner_connection() -> psycopg.Connection:
    return psycopg.connect(
        host=config.DB_HOST,
        port=config.DB_PORT,
        dbname=config.DB_NAME,
        user=config.DB_OWNER_USER,
        password=config.DB_OWNER_PASSWORD,
    )


def readonly_connection() -> psycopg.Connection:
    return psycopg.connect(
        host=config.DB_HOST,
        port=config.DB_PORT,
        dbname=config.DB_NAME,
        user=config.DB_READONLY_USER,
        password=config.DB_READONLY_PASSWORD,
    )


def json_value(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, date):
        return value.isoformat()
    return value
