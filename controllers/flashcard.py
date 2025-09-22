from fastapi import UploadFile, APIRouter, Depends, File
from controllers.auth import getCurrentUser
from fastapi.responses import JSONResponse
from models.flashCardModel import processFlashcards
from connection import prismaConnection as db
import tempfile
import os
import fitz  # PyMuPDF
import easyocr
import math
import logging
import json

from services.redis_service import redis_service  # 🔑 usa seu RedisService

# Configuração do Logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter(
    prefix='/logic',
    tags=['logic']
)

# --- OCR: inicializado apenas 1 vez ---
try:
    logger.info("Inicializando o leitor EasyOCR...")
    ocr_reader = easyocr.Reader(['pt'], gpu=False)
    logger.info("Leitor EasyOCR inicializado com sucesso.")
except Exception as e:
    logger.error(f"Falha ao inicializar o EasyOCR: {e}")
    ocr_reader = None


# -------------------------------------------------------------------
# FUNÇÃO PESADA (executada pelo worker)
# -------------------------------------------------------------------
async def process_pdf_and_create_flashcards(
    pdf_content: bytes,
    pdf_filename: str,
    user_id: str,
    tokens_to_deduct: int,
    pdf_record_id: int
):
    temp_file_path = ""

    try:
        logger.info(f"[UserID: {user_id}] Iniciando processamento do PDF: {pdf_filename}")

        # Salvar PDF temporário
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_file:
            temp_file.write(pdf_content)
            temp_file_path = temp_file.name

        doc = fitz.open(temp_file_path)
        full_text = ""

        for page_num, page in enumerate(doc):
            text = page.get_text()
            if text.strip():
                full_text += text + "\n\n"
            else:
                if not ocr_reader:
                    logger.warning("OCR indisponível, pulando página.")
                    continue

                pix = page.get_pixmap()
                img_path = temp_file_path.replace(".pdf", f"_page_{page.number}.png")
                pix.save(img_path)

                ocr_result = ocr_reader.readtext(img_path, detail=0)
                full_text += "\n".join(ocr_result) + "\n\n"
                os.remove(img_path)

        markdown_content = f"# Conteúdo do PDF: {pdf_filename}\n\n{full_text}"

        # Atualiza o texto extraído
        await db.prisma.pdf.update(
            where={"id": pdf_record_id},
            data={"extracted_text": markdown_content}
        )

        # Gera flashcards
        flashcard_result = await processFlashcards(markdown_content, {"id": user_id})
        flashcards = flashcard_result.get("flashcards", [])

        if flashcards:
            await db.prisma.flashcard.create_many(
                data=[{"pdfId": pdf_record_id, "front": f["front"], "back": f["back"]} for f in flashcards]
            )
            logger.info(f"[UserID: {user_id}] {len(flashcards)} flashcards criados.")
        else:
            logger.warning(f"[UserID: {user_id}] Nenhum flashcard gerado.")

        # Debita tokens
        await db.prisma.user.update(
            where={'id': user_id},
            data={'tokens': {'decrement': tokens_to_deduct}}
        )

        # Atualiza status
        await db.prisma.pdf.update(
            where={"id": pdf_record_id},
            data={"status": "processed"}
        )

    except Exception as e:
        logger.error(f"Erro processando PDF {pdf_record_id}: {e}", exc_info=True)
        await db.prisma.pdf.update(
            where={"id": pdf_record_id},
            data={"status": "failed"}
        )
    finally:
        if temp_file_path and os.path.exists(temp_file_path):
            os.unlink(temp_file_path)


# -------------------------------------------------------------------
# ROTA PARA RECEBER PDF (enfileira no Redis)
# -------------------------------------------------------------------
# -------------------------------------------------------------------
# ROTA PARA RECEBER PDF (enfileira no Redis) – ATUALIZADA
# -------------------------------------------------------------------
@router.post('/flashcards')
async def handle_flashcard_pdf(
    current_user: dict = Depends(getCurrentUser),
    pdf: UploadFile = File(...)
):
    if not current_user:
        return JSONResponse({"success": False, "detail": "Usuário não autenticado"}, status_code=401)

    if not pdf or pdf.content_type != "application/pdf":
        return JSONResponse({"success": False, "detail": "Arquivo inválido"}, status_code=400)

    # Ler PDF em bytes
    pdf_content = await pdf.read()

    file_size_in_bytes = len(pdf_content)
    bytes_per_token = 409600
    tokens_needed = math.ceil(file_size_in_bytes / bytes_per_token)

    user = await db.prisma.user.find_unique(where={'id': current_user["id"]})
    if not user or user.tokens < tokens_needed:
        return JSONResponse({
            "success": False,
            "detail": f"Tokens insuficientes. Necessário: {tokens_needed}, Disponível: {user.tokens if user else 0}"
        }, status_code=402)

    # Cria registro inicial
    pdf_record = await db.prisma.pdf.create(
        data={
            "name": pdf.filename,
            "userId": current_user["id"],
            "extracted_text": ""
        }
    )

    # Converte PDF para base64 ASCII seguro
    import base64
    encoded_pdf = base64.b64encode(pdf_content).decode("ascii")

    # Enfileira no Redis
    redis_service.enqueue_task("pdf_processing_queue", {
        "pdf_content": encoded_pdf,
        "pdf_filename": pdf.filename,
        "user_id": current_user["id"],
        "tokens_to_deduct": tokens_needed,
        "pdf_record_id": pdf_record.id
    })

    return JSONResponse({
        "success": True,
        "detail": "PDF enfileirado para processamento.",
        "pdf_id": pdf_record.id,
        "tokens_needed": tokens_needed,
        "current_tokens": user.tokens,
    }, status_code=202)

# -------------------------------------------------------------------
# ROTA PARA CONSULTAR STATUS
# -------------------------------------------------------------------
@router.get('/flashcards/{pdf_id}/status')
async def get_pdf_status(pdf_id: str, current_user: dict = Depends(getCurrentUser)):
    if not current_user:
        return JSONResponse({"success": False, "detail": "Usuário não autenticado"}, status_code=401)

    try:
        pdf_id = int(pdf_id)
    except ValueError:
        return JSONResponse({"success": False, "detail": "ID inválido"}, status_code=400)

    pdf = await db.prisma.pdf.find_first(
        where={'id': pdf_id, 'userId': current_user['id']}
    )
    if not pdf:
        return JSONResponse({"success": False, "detail": "PDF não encontrado"}, status_code=404)

    return JSONResponse({"success": True, "status": pdf.status}, status_code=200)
