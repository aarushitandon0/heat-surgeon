"""FastAPI application: CORS and router wiring."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import calibrate, optimize, street

app = FastAPI(title="Heat Surgeon")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(street.router)
app.include_router(calibrate.router)
app.include_router(optimize.router)
