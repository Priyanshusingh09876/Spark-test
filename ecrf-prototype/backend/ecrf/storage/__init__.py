"""Persistence. JSON for drafts being edited, relational for readings.

SQLite by default so the prototype runs with zero setup. Postgres is a
DATABASE_URL change; SQLAlchemy's JSON type works on both.
"""
