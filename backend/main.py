# backend/main.py

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from dotenv import load_dotenv

import traceback

from app.auth.routes import router as auth_router
from app.routes import router as app_router  # <-- all non-auth endpoints live here

# Load env from backend/.env
load_dotenv(override=True)

app = FastAPI()


@app.exception_handler(Exception)
async def unhandled_exception_handler(request, exc):
    # Dev-friendly: show stack trace in server logs and return detail in response.
    print("\n" + "=" * 80)
    print("UNHANDLED EXCEPTION:", str(exc))
    traceback.print_exc()
    print("=" * 80 + "\n")
    return JSONResponse(
        status_code=500,
        content={"detail": f"Internal Server Error: {str(exc)}"},
    )

# CORS (keep minimal + explicit)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers only (NO business logic here)
app.include_router(auth_router)
app.include_router(app_router)