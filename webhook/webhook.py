from connection import prismaConnection as db
from fastapi import APIRouter, Request, HTTPException
import mercadopago
import os
import logging

router = APIRouter(
    prefix="/webhook",
    tags=["webhook"]
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mercadopago_webhook")

sdk = mercadopago.SDK(os.getenv("MP_ACESS_TOKEN"))

@router.post("/mercadopago")
async def mercadopago_webhook(request: Request):
    payload = await request.json()
    logger.info(f"Webhook recebido: {payload}")

    # Apenas processa notificações de pagamento
    if payload.get("type") == "payment":
        payment_id = payload.get("data", {}).get("id")
        if not payment_id:
            logger.warning("Webhook de pagamento sem ID de dados.")
            return {"status": "ignored"}

        try:
            # Consulta detalhes do pagamento no Mercado Pago
            payment_info = sdk.payment().get(payment_id)
            if payment_info["status"] != 200:
                logger.error(f"Erro ao buscar pagamento {payment_id} no MP: {payment_info['response']}")
                return {"status": "error", "detail": "MP API error"}

            payment_data = payment_info["response"]
            status = payment_data["status"]
            mp_payment_id = str(payment_data["id"])

            # Busca o pagamento no nosso banco que ainda não teve os tokens adicionados
            payment_record = await db.prisma.payment.find_first(
                where={"mpPaymentId": mp_payment_id, "tokensAdd": False},
                include={"product": True},
            )

            if not payment_record:
                logger.info(f"Pagamento {mp_payment_id} não encontrado ou já processado.")
                return {"status": "ok", "detail": "Pagamento não encontrado ou já processado."}

            # Se o pagamento foi aprovado, adiciona os tokens e atualiza o status
            if status == "approved":
                tokens_to_add = payment_record.product.tokens
                user_id = payment_record.userId

                async with db.prisma.tx() as transaction:
                    # Adiciona os tokens ao usuário
                    await transaction.user.update(
                        where={"id": user_id},
                        data={"tokens": {"increment": tokens_to_add}},
                    )
                    # Atualiza o pagamento no banco
                    await transaction.payment.update(
                        where={"id": payment_record.id},
                        data={"status": "approved", "tokensAdd": True},
                    )
                logger.info(f"Pagamento {mp_payment_id} aprovado. {tokens_to_add} tokens adicionados ao usuário {user_id}.")
            # Para outros status (rejeitado, cancelado, etc.), apenas atualizamos no nosso banco
            elif status in ["rejected", "cancelled", "failed"]:
                await db.prisma.payment.update(
                    where={"id": payment_record.id}, data={"status": status}
                )
                logger.info(f"Pagamento {mp_payment_id} atualizado para {status}")

        except Exception as e:
            logger.error(f"Erro ao processar webhook para pagamento {payment_id}: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="Erro interno ao processar webhook")

        return {"status": "ok"}

    return {"status": "ignored"}
