# Load .env (if present) so PK_* settings in it actually take effect. Existing
# environment variables win, so `PK_MEMORY_BACKEND=local make test` still works.
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:  # python-dotenv is optional at import time
    pass
