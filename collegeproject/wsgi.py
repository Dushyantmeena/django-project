import os
import sys
from pathlib import Path
from django.core.wsgi import get_wsgi_application
from dotenv import load_dotenv

# Add the project root to the python path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# Load .env file
load_dotenv(BASE_DIR / '.env')

# Django settings module
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'collegeproject.settings')

# WSGI application
application = get_wsgi_application()
