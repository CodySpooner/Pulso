import os

import uvicorn

from pulso_core.settings import get_settings


def main() -> None:
    uvicorn.run(
        "pulso_api.main:app",
        host="::",
        port=int(os.getenv("PORT", str(get_settings().api_port))),
        access_log=False,
    )


if __name__ == "__main__":
    main()
