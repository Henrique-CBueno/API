from fastapi import APIRouter, HTTPException, Depends
from connection import prismaConnection as db
from controllers.auth import getCurrentUser

import mercadopago
import os

router = APIRouter(
    prefix='/payment',
    tags=['payment']
)

sdk = mercadopago.SDK(os.getenv("MP_ACESS_TOKEN"))

@router.post("/pagamentos/{product_id}")
async def criar_pagamento(product_id: int, user: dict = Depends(getCurrentUser)):

    if user is None:
        return JSONResponse(content={"success": False, "detail": "Usuário não autenticado"}, status_code=401)

    # busca produto no banco
    product = await db.prisma.product.find_unique(where={"id": product_id})
    if not product:
        raise HTTPException(status_code=404, detail="Produto não encontrado")

    # cria preferência no Mercado Pago
    preference_data = {
        "items": [
            {
                "title": product.name,
                "quantity": 1,
                "unit_price": product.price
            }
        ],
        "payment_methods": {
            "excluded_payment_types": [
                { "id": "ticket" },
                { "id": "atm" }     
            ],
            "excluded_payment_methods": [
                { "id": "master" },
                { "id": "amex" },
                { "id": "elo" },
                { "id": "hipercard" }
            ]
        },
        # PRECISA DE DOMINIO HTTPS
        # "back_urls": {
        #     "success": "http://localhost:5173/pagamento/sucesso",
        #     "failure": "http://localhost:5173/pagamento/falha",
        #     "pending": "http://localhost:5173/pagamento/pendente",
        # },
        # "auto_return": "approved",
        # "notification_url": "https://mutagenetic-uninstinctively-miles.ngrok-free.app/webhook"
    }

    preference_response = sdk.preference().create(preference_data)
    # ADICIONE ESTA LINHA PARA VER O ERRO
    print(preference_response) 

# Verifique se a resposta contém o ID antes de continuar
    if "id" not in preference_response["response"]:
        raise HTTPException(status_code=400, detail=f"Erro ao criar preferência: {preference_response['response']}")
    preference = preference_response["response"]

    # cria registro no banco
    pagamento = await db.prisma.payment.create(
        data={
            "userId": user["id"],
            "productId": product.id,
            "amount": product.price,
            "status": "pending",
            "mpPaymentId": preference["id"]
        }
    )


    return {
        "init_point": preference["init_point"]
    }