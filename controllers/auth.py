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
from services.email_service import email_service
from services.redis_service import redis_service

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

class VerifyOTPRequest(BaseModel):
    email: str
    otp_code: str

class ResendOTPRequest(BaseModel):
    email: str


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def createUser(createUserRequest: CreateUserRequest):
    """Endpoint para criar (registrar) um novo usuário e enviar OTP."""
    existing_user = await prismaConnection.prisma.user.find_unique(where={'email': createUserRequest.email})
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email já registrado."
        )

    hashed_password = bcrypt_context.hash(createUserRequest.password)
    
    # Criar usuário com is_verified = False
    new_user = await prismaConnection.prisma.user.create(
        data={
            "email": createUserRequest.email,
            "password": hashed_password,
            "is_verified": False
        }
    )
    
    # Gerar e enviar OTP
    otp_code = email_service.generate_otp()
    
    # Armazenar OTP no Redis
    redis_service.store_otp(createUserRequest.email, otp_code, new_user.id)
    
    # Enviar email com OTP
    email_sent = await email_service.send_otp_email(createUserRequest.email, otp_code)
    
    if not email_sent:
        # Se falhou ao enviar email, deletar usuário criado
        await prismaConnection.prisma.user.delete(where={'id': new_user.id})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao enviar email de verificação. Tente novamente."
        )
    
    return {
        "message": "Usuário criado com sucesso. Verifique seu email para o código de verificação.",
        "email": new_user.email,
        "requires_verification": True
    }

@router.post("/verify-otp", status_code=status.HTTP_200_OK)
async def verifyOTP(verifyOTPRequest: VerifyOTPRequest):
    """Endpoint para verificar código OTP e ativar conta do usuário."""
    # Verificar OTP no Redis
    otp_result = redis_service.verify_otp(verifyOTPRequest.email, verifyOTPRequest.otp_code)
    
    if not otp_result["valid"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=otp_result["message"]
        )
    
    # Atualizar usuário para is_verified = True
    await prismaConnection.prisma.user.update(
        where={'id': otp_result["user_id"]},
        data={'is_verified': True}
    )
    
    return {
        "message": "Email verificado com sucesso! Sua conta foi ativada.",
        "email": verifyOTPRequest.email
    }

@router.post("/resend-otp", status_code=status.HTTP_200_OK)
async def resendOTP(resendOTPRequest: ResendOTPRequest):
    """Endpoint para reenviar código OTP."""
    # Verificar se usuário existe e não está verificado
    user = await prismaConnection.prisma.user.find_unique(
        where={'email': resendOTPRequest.email}
    )
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuário não encontrado."
        )
    
    if user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Usuário já está verificado."
        )
    
    # Gerar novo OTP
    otp_code = email_service.generate_otp()
    
    # Armazenar novo OTP no Redis
    redis_service.store_otp(resendOTPRequest.email, otp_code, user.id)
    
    # Enviar email com novo OTP
    email_sent = await email_service.send_otp_email(resendOTPRequest.email, otp_code)
    
    if not email_sent:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao reenviar email de verificação. Tente novamente."
        )
    
    return {
        "message": "Código de verificação reenviado com sucesso.",
        "email": resendOTPRequest.email
    }

@router.post("/token", response_model=Token)
async def loginForAcessToken(formData: Annotated[OAuth2PasswordRequestForm, Depends()]):
    user = await authenticateUser(formData.username, formData.password)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='o email ou a senha esta incorreto')
    
    # Verificar se usuário está verificado
    if not user.is_verified:
        # Gerar e enviar OTP automaticamente
        otp_code = email_service.generate_otp()
        
        # Armazenar OTP no Redis
        redis_service.store_otp(user.email, otp_code, user.id)
        
        # Enviar email com OTP
        email_sent = await email_service.send_otp_email(user.email, otp_code)
        
        if not email_sent:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail='Erro ao enviar código de verificação. Tente novamente.'
            )
        
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail='Conta não verificada. Um novo código de verificação foi enviado para seu email.'
        )
    
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
                    },
                    "order_by": {
                        "createdAt": "desc"  # do mais novo para o mais velho
                    }
                }
            }
        )
        
        # Verificar se usuário existe e está verificado
        if not user_with_pdfs_and_flashcards:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="usuário não encontrado")
        
        if not user_with_pdfs_and_flashcards.is_verified:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, 
                detail="conta não verificada. verifique seu email para ativar sua conta"
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
                    'pdfStatus': pdf.status,
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


class ResetPasswordRequest(BaseModel):
    email: str

class ResetPasswordVerifyOTPRequest(BaseModel):
    email: str
    otp_code: str

class ResetPasswordConfirmRequest(BaseModel):
    new_password: str


@router.post("/reset-password/request", status_code=status.HTTP_200_OK)
async def requestPasswordReset(resetRequest: ResetPasswordRequest):
    """Inicia o fluxo de reset de senha: gera OTP e envia por email."""
    user = await prismaConnection.prisma.user.find_unique(where={'email': resetRequest.email})
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuário não encontrado."
        )

    otp_code = email_service.generate_otp()
    redis_service.store_otp(resetRequest.email, otp_code, user.id)

    email_sent = await email_service.send_otp_email(resetRequest.email, otp_code)
    if not email_sent:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao enviar OTP para reset de senha."
        )

    return {"message": "Um código OTP foi enviado para seu email."}


@router.post("/reset-password/verify-otp", status_code=status.HTTP_200_OK)
async def verifyResetPasswordOTP(verifyRequest: ResetPasswordVerifyOTPRequest):
    """Verifica OTP e retorna JWT temporário para permitir troca de senha."""
    otp_result = redis_service.verify_otp(verifyRequest.email, verifyRequest.otp_code)

    if not otp_result["valid"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=otp_result["message"]
        )

    # Criar JWT temporário só para reset de senha
    reset_token = createAccessToken(
        verifyRequest.email,
        otp_result["user_id"],
        expiresDelta=timedelta(minutes=10)  # expira em 10min
    )

    return {"reset_token": reset_token, "token_type": "bearer"}


@router.post("/reset-password/confirm", status_code=status.HTTP_200_OK)
async def confirmResetPassword(
    resetConfirm: ResetPasswordConfirmRequest,
    token: Annotated[str, Depends(oauth2_bearer)]
):
    """Confirma a nova senha, usando JWT temporário."""
    try:
        payload = jwt.decode(token, os.getenv("SECRET_KEY"), algorithms=[os.getenv("ALGORITHM")])
        email: str = payload.get("sub")
        user_id: int = payload.get("id")

        if not email or not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido.")

    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido ou expirado.")

    # Atualizar senha no DB
    hashed_password = bcrypt_context.hash(resetConfirm.new_password)
    await prismaConnection.prisma.user.update(
        where={'id': user_id},
        data={'password': hashed_password}
    )

    return {"message": "Senha redefinida com sucesso."}



