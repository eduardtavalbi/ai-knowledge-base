from app.db.migration_url import render_alembic_database_url


def test_alembic_database_url_preserves_password_for_migrations():
    rendered = render_alembic_database_url(
        "postgresql+asyncpg://postgres:integration-secret@db:5432/knowledge_base"
    )

    assert rendered == (
        "postgresql+psycopg2://postgres:integration-secret@db:5432/knowledge_base"
    )
    assert ":***@" not in rendered


def test_alembic_database_url_escapes_percent_for_config_parser():
    rendered = render_alembic_database_url(
        "postgresql+asyncpg://postgres:p%25ss@db:5432/knowledge_base"
    )

    assert "postgres:p%%25ss@db" in rendered
