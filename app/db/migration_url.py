from sqlalchemy.engine import make_url


def render_alembic_database_url(database_url_value: str) -> str:
    """Render a synchronous Alembic URL without masking its password.

    ConfigParser treats percent signs as interpolation markers, so escape
    them after rendering the real URL for Alembic's ini configuration.
    """
    database_url = make_url(database_url_value).set(
        drivername="postgresql+psycopg2"
    )
    return database_url.render_as_string(hide_password=False).replace("%", "%%")
