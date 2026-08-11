import uvicorn

from .config import settings

if __name__ == "__main__":
    uvicorn.run("gyrus.api:app", host=settings.host, port=settings.port)
