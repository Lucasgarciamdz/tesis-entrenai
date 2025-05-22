# We need to handle the routers import differently since it doesn't have an __init__.py
# but it's still used in the API
from . import models

__all__ = ["models"]
