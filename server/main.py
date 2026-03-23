# main.py - Application entry point
from dotenv import load_dotenv

# Load environment variables before other imports
load_dotenv()

import uvicorn
from api import app
from config import settings

if __name__ == "__main__":
    uvicorn.run(
        app,
        host=settings.api_host,
        port=settings.api_port
    )
