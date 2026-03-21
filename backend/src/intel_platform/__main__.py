import uvicorn
from intel_platform.config import get_settings

if __name__ == "__main__":
    s = get_settings()
    uvicorn.run(
        "intel_platform.api.app:app",
        host=s.api_host,
        port=s.api_port,
        reload=True,
    )
