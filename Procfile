release: python -c "from app.db import UserDB; UserDB().init_schema()"
web: uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
