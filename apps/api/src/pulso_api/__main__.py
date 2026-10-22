import os
import socket

import uvicorn

from pulso_core.settings import get_settings


def main() -> None:
    port = int(os.getenv("PORT", str(get_settings().api_port)))
    config = uvicorn.Config(
        "pulso_api.main:app",
        host="::",
        port=port,
        access_log=False,
    )
    # Uvicorn's host-only path sets IPV6_V6ONLY; supply an explicitly dual-stack socket.
    with socket.create_server(
        ("::", port), family=socket.AF_INET6, dualstack_ipv6=True
    ) as listener:
        uvicorn.Server(config).run(sockets=[listener])


if __name__ == "__main__":
    main()
