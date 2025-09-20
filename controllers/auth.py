from datetime import timedelta, datetime
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from starlette import status
from passlib.context import CryptContext
from fastapi.security import OAuth2PasswordRequestForm, OAuth2PasswordBearer
from jose import jwt, JWTError
from connection import prismaConnection
from datetime import datetime
import pytz
from dotenv import load_dotenv
import os

load_dotenv()


router = APIRouter(
    prefix='/auth',
    tags=['auth']
)



bcrypt_context = CryptContext(schemes=['bcrypt'], deprecated='auto')
oauth2_bearer = OAuth2PasswordBearer(tokenUrl='auth/token')

class CreateUserRequest(BaseModel):
    email: str
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def createUser(createUserRequest: CreateUserRequest):
    """Endpoint para criar (registrar) um novo usuário."""
    existing_user = await prismaConnection.prisma.user.find_unique(where={'email': createUserRequest.email})
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email já registrado."
        )

    hashed_password = bcrypt_context.hash(createUserRequest.password)
    
    new_user = await prismaConnection.prisma.user.create(
        data={
            "email": createUserRequest.email,
            "password": hashed_password
        }
    )
    return {"id": new_user.id, "email": new_user.email}

@router.post("/token", response_model=Token)
async def loginForAcessToken(formData: Annotated[OAuth2PasswordRequestForm, Depends()]):
    user = await authenticateUser(formData.username, formData.password)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='o email ou a senha esta incorreto')
    token = createAccessToken(user.email, user.id, timedelta(minutes=60))
    return {"access_token": token, "token_type": "bearer"}



async def authenticateUser(username: str, password: str):
    user = await prismaConnection.prisma.user.find_first(
        where={
            "email": username
        }
    )
    if not user:
        return False
    if not bcrypt_context.verify(password, user.password):
        return False
    return user


def createAccessToken(email: str, id: int, expiresDelta: timedelta):
    encode = {'sub' : email, 'id': id}
    expires = datetime.utcnow() + expiresDelta
    encode.update({'exp': expires})
    return jwt.encode(encode, os.getenv("SECRET_KEY"), algorithm=os.getenv("ALGORITHM"))


async def getCurrentUser(token: Annotated[str, Depends(oauth2_bearer)]):
    try:
        payload = jwt.decode(token, os.getenv("SECRET_KEY"), algorithms=[os.getenv("ALGORITHM")])
        username: str = payload.get('sub')
        id: int = payload.get('id')
        tokens: int = payload.get('tokens')
        if username is None or id is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="não foi possivel validar o usuario")

        user_with_pdfs_and_flashcards = await prismaConnection.prisma.user.find_unique(
            where={'id': id},
            include={
                'pdfs': {
                    'include': {
                        'flashcards': True  # traz todos os flashcards do PDF
                    }
                }
            }
        )

        # NAO ENVIAR AS PASSWORDS
        user_dict = {
            'id': user_with_pdfs_and_flashcards.id,
            'email': user_with_pdfs_and_flashcards.email,
            'tokens': user_with_pdfs_and_flashcards.tokens,
            'role': user_with_pdfs_and_flashcards.role,
            'pdfs': [
                {
                    'id': pdf.id,
                    'name': pdf.name,
                    'createdAt': pdf.createdAt,
                    'flashcards': [
                        {
                            'id': fc.id,
                            'front': fc.front,
                            'back': fc.back
                        } for fc in pdf.flashcards
                    ]
                } for pdf in user_with_pdfs_and_flashcards.pdfs
            ]
        }

        for pdf in user_dict['pdfs']:
            createdAtUtc = pdf['createdAt']
            brasiliaDatetime = createdAtUtc.astimezone(pytz.timezone("America/Sao_Paulo"))
            pdf['createdAt'] = brasiliaDatetime.strftime('%d/%m/%Y %H:%M:%S')
        
        return user_dict
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="nao foi possivel validar o usuario")


