from fastapi import HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from connection import prismaConnection
from dotenv import load_dotenv
import os

load_dotenv()

oauth2_bearer = OAuth2PasswordBearer(tokenUrl='auth/token')

async def verify_user_verification(token: str):
    """Middleware para verificar se o usuário está verificado"""
    try:
        payload = jwt.decode(token, os.getenv("SECRET_KEY"), algorithms=[os.getenv("ALGORITHM")])
        user_id = payload.get('id')
        
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, 
                detail="Token inválido"
            )
        
        # Buscar usuário no banco
        user = await prismaConnection.prisma.user.find_unique(
            where={'id': user_id}
        )
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, 
                detail="Usuário não encontrado"
            )
        
        if not user.is_verified:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, 
                detail="Conta não verificada. Verifique seu email para ativar sua conta."
            )
        
        return user
        
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail="Token inválido"
        )
