from fastapi import FastAPI, Depends, HTTPException
from contextlib import asynccontextmanager
from typing import Annotated
from fastapi.middleware.cors import CORSMiddleware
import os
import uvicorn

from connection import prismaConnection
from controllers import auth, flashcard, payments
from controllers.auth import getCurrentUser


@asynccontextmanager
async def lifespan(app: FastAPI):
    await prismaConnection.connect()
    yield
    await prismaConnection.disconnect()

app = FastAPI(lifespan=lifespan)
app.include_router(auth.router)
app.include_router(flashcard.router)
app.include_router(payments.router)

origins = os.getenv("BACKEND_CORS_ORIGINS")

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,  # Allows specified origins
    allow_credentials=True, # Allows cookies and authentication headers
    allow_methods=["*"],    # Allows all methods (GET, POST, etc.)
    allow_headers=["*"],    # Allows all headers
)

 

user_dependency = Annotated[dict, Depends(getCurrentUser)]

@app.get("/")
async def root(user: user_dependency):
    if user is None:
        raise HTTPException(status_code=401, detail='auth failed')
    return {"User": user}






if __name__ == '__main__':
    # Evite iniciar um segundo servidor localmente quando usando Docker/uvicorn externo
    # Prefira: `uvicorn app:app --reload`
    pass