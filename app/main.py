from fastapi import FastAPI

from app.database import create_db_and_tables
from app.seed import seed_data

app = FastAPI(title="Cruise Booking System")


@app.on_event("startup")
def startup_event():
    create_db_and_tables()
    seed_data()


@app.get("/health")
def health_check():
    return {"status": "ok"}
