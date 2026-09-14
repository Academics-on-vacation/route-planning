from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL


class Settings(BaseSettings):
    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = Field(
        default="route_planning", validation_alias=AliasChoices("DB_NAME", "POSTGRES_DB")
    )
    db_user: str = Field(
        default="route_planning", validation_alias=AliasChoices("DB_USER", "POSTGRES_USER")
    )
    db_password: str = Field(validation_alias=AliasChoices("DB_PASSWORD", "POSTGRES_PASSWORD"))

    model_config = SettingsConfigDict(
        extra="ignore",
        populate_by_name=True,
    )

    @property
    def database_url(self) -> URL:
        return URL.create(
            drivername="postgresql+asyncpg",
            username=self.db_user,
            password=self.db_password,
            host=self.db_host,
            port=self.db_port,
            database=self.db_name,
        )


settings = Settings()
