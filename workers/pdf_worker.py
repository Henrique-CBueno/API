import asyncio
import base64
import logging
from services.redis_service import redis_service
from controllers.flashcard import process_pdf_and_create_flashcards
from connection import prismaConnection as db

# Configuração do Logger
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("pdf_worker")

async def worker_loop():
    logger.info("Worker iniciado. Preparando conexão com Prisma...")

    # Conecta apenas uma vez
    try:
        await db.prisma.connect()
        logger.info("Conexão com Prisma estabelecida.")
    except Exception as e:
        logger.error(f"Falha ao conectar Prisma: {e}", exc_info=True)
        return

    try:
        while True:
            task = redis_service.dequeue_task("pdf_processing_queue")
            if task:
                logger.info(f"Tarefa encontrada: {task['pdf_filename']} para user {task['user_id']}")
                try:
                    pdf_content = base64.b64decode(task["pdf_content"])
                    await process_pdf_and_create_flashcards(
                        pdf_content,
                        task["pdf_filename"],
                        task["user_id"],
                        task["tokens_to_deduct"],
                        task["pdf_record_id"]
                    )
                    logger.info(f"Tarefa {task['pdf_filename']} concluída com sucesso.")
                except Exception as e:
                    logger.error(f"Erro processando tarefa {task['pdf_filename']}: {e}", exc_info=True)
            else:
                await asyncio.sleep(2)

    finally:
        if await db.prisma.is_connected():
            await db.prisma.disconnect()
            logger.info("Conexão Prisma encerrada.")

if __name__ == "__main__":
    logger.info("Iniciando worker async com asyncio.run()...")
    asyncio.run(worker_loop())
