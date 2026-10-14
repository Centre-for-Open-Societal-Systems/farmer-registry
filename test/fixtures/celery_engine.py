from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from .config import Settings

_config = Settings.get_config()


def _pool_kwargs(datasource: str) -> dict:
    if not datasource or datasource.startswith("sqlite"):
        return {}
    return {
        "pool_pre_ping": _config.db_pool_pre_ping,
        "pool_recycle": _config.db_pool_recycle,
        "pool_size": _config.db_pool_size,
        "max_overflow": _config.db_pool_max_overflow,
    }


class Engine:
    """
    Engine for sync database connection.
    Engine for async connection is managed here (celery workers do not use
    openg2p_fastapi_common.context dbengine).
    """

    _sync_engine = None
    _async_engine = None
    _async_session_maker = None

    @staticmethod
    def get_engine():
        if Engine._sync_engine is None:
            datasource = Engine.construct_db_datasource()
            try:
                Engine._sync_engine = create_engine(datasource, **_pool_kwargs(datasource))
            except Exception as e:
                raise ValueError(f"Invalid DB datasource: {datasource} | ERROR: {e}")
        return Engine._sync_engine

    @staticmethod
    def get_async_engine():
        if Engine._async_engine is None:
            datasource = Engine.construct_async_db_datasource()
            try:
                Engine._async_engine = create_async_engine(datasource, **_pool_kwargs(datasource))
            except Exception as e:
                raise ValueError(f"Invalid DB datasource: {datasource} | ERROR: {e}")
        return Engine._async_engine

    @staticmethod
    def get_async_session_maker():
        if Engine._async_session_maker is None:
            Engine._async_session_maker = async_sessionmaker(
                bind=Engine.get_async_engine(), expire_on_commit=False
            )
        return Engine._async_session_maker

    def construct_db_datasource():
        return f"postgresql+psycopg2://{_config.db_username}:{_config.db_password}@{_config.db_hostname}:{_config.db_port}/{_config.db_dbname}"

    def construct_async_db_datasource():
        return f"postgresql+asyncpg://{_config.db_username}:{_config.db_password}@{_config.db_hostname}:{_config.db_port}/{_config.db_dbname}"
