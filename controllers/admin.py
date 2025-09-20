from fastapi import APIRouter, Depends, HTTPException, Request
from controllers.auth import getCurrentUser
from fastapi.responses import JSONResponse
from connection import prismaConnection as db


router = APIRouter(
    prefix='/admin',
    tags=['admin']
)



@router.get('/getUsers')
async def getUsers(current_user: dict = Depends(getCurrentUser)):
    if not current_user or current_user["role"] != 'admin':
        raise HTTPException(status_code=403, detail="Acesso negado.")
    users = await db.prisma.user.find_many(
        include={"pdfs": True},  # precisa incluir pdfs se quiser contar
        order={"tokens": "desc"},  # ordena pelos tokens
    )
    safe_users = [
        {
            "id": u.id,
            "email": u.email,
            "tokens": u.tokens,
            "createdAt": u.createdAt,
            "pdfsUploaded": len(u.pdfs) if u.pdfs else 0,
        }
        for u in users
    ]
    return {"users": safe_users}
    


@router.patch("/users/{user_id}/tokens")
async def update_user_tokens(
    user_id: int,
    request: Request,
    current_user: dict = Depends(getCurrentUser)
):
    # Verifica se o usuário logado é admin
    if not current_user or current_user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Acesso negado.")

    # Busca o usuário
    user = await db.prisma.user.find_unique(where={"id": user_id})
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")
    
    body = await request.json()
    tokens = body.get("tokens")
    print(f"Atualizando tokens do usuário {user_id} para {tokens}")

    if tokens is None:
        raise HTTPException(status_code=400, detail="Campo 'tokens' é obrigatório")

    # Atualiza os tokens
    updated_user = await db.prisma.user.update(
        where={"id": user_id},
        data={"tokens": tokens}
    )

    return JSONResponse(content={"message": "Tokens atualizados com sucesso.", "user": {
        "id": updated_user.id,
        "tokens": updated_user.tokens
    }})