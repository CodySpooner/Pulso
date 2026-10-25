from typing import Annotated

from pydantic import StringConstraints

# Postgres text can't hold NUL: free text refuses it with a 422 before any SQL (DEC-287).
NoNulStr = Annotated[str, StringConstraints(pattern=r"^[^\x00]*$")]
