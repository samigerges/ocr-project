from pydantic import BaseModel
import os


class Settings(BaseModel):
    # Where we store all doc artifacts (original/pages/processed/results)
    storage_dir: str = os.getenv("OCR_STORAGE_DIR", "storage")


settings = Settings()
