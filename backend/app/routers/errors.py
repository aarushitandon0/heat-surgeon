"""Map data-layer failures to HTTP errors that say plainly what is missing. Nothing falls back to invented data."""

from contextlib import contextmanager

from fastapi import HTTPException

from app.data.cache import CacheMiss
from app.pipeline import UnpricedBudget, street_ids


@contextmanager
def known_street(street_id: str):
    if street_id not in street_ids():
        raise HTTPException(status_code=404, detail=f"No street {street_id!r}. Known streets: {', '.join(street_ids())}.")
    try:
        yield
    except CacheMiss as error:
        raise HTTPException(status_code=503, detail=f"No cached data for {street_id}, and live data is off. {error}")
    except UnpricedBudget as error:
        raise HTTPException(status_code=422, detail=str(error))
