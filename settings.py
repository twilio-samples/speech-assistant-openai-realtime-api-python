import os
from typing import Optional

from dotenv import load_dotenv

load_dotenv()


def _get_or_raise(env_var_name: str) -> str:
    """Retrieves an environment variable, raising an error if it is not set.

    Args:
        env_var_name (str): Name of the variable.

    Raises:
        ValueError: if the variable is not set.

    Returns:
        str: Value of `env_var_name`
    """
    value: Optional[str] = os.getenv(env_var_name)
    if value:
        return value
    raise ValueError(
        f"Missing {env_var_name}. Please set it in the .env file.")


# OpenAI key with realtime access (i.e. non-trial)
OPENAI_API_KEY: str = _get_or_raise("OPENAI_API_KEY")
# Twilio account credentials with active source phone number
TWILIO_ACCOUNT_SID: str = _get_or_raise("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN: str = _get_or_raise("TWILIO_AUTH_TOKEN")
