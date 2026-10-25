from functools import lru_cache
from urllib.parse import quote

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL


class Settings(BaseSettings):
    environment: str = "development"
    host: str = "0.0.0.0"  # nosec B104 # must bind all interfaces to be reachable inside the Docker network
    port: int = 8080

    database_host: str
    database_port: int = 5432
    database_name: str
    database_user: str
    database_password: str

    rabbitmq_host: str = "rabbitmq"
    rabbitmq_port: int = 5672
    rabbitmq_user: str = "admin"
    rabbitmq_password: str = "admin"
    rabbitmq_exchange: str = "server.events"

    # Íconos de servidor (S3). En EC2 las credenciales salen del rol de la instancia; en local, de
    # AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY o de AWS_PROFILE (los lee boto3, no esta clase).
    aws_region: str = "us-east-1"
    s3_bucket: str = ""
    s3_public_base_url: str = ""  # vacío: https://<bucket>.s3.<region>.amazonaws.com

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def database_url(self) -> str:
        return URL.create(
            drivername="postgresql+asyncpg",
            username=self.database_user,
            password=self.database_password,
            host=self.database_host,
            port=self.database_port,
            database=self.database_name,
        ).render_as_string(hide_password=False)

    @property
    def rabbitmq_url(self) -> str:
        """AMQP URL for the default vhost. Credentials are percent-encoded, like in database_url."""
        user = quote(self.rabbitmq_user, safe="")
        password = quote(self.rabbitmq_password, safe="")
        return f"amqp://{user}:{password}@{self.rabbitmq_host}:{self.rabbitmq_port}/"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
