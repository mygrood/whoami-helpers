import sys
from pathlib import Path

# Add the project directory to the Python path
project_path = Path(__file__).parent.absolute()
if str(project_path) not in sys.path:
    sys.path.insert(0, str(project_path))

from app import app as application 