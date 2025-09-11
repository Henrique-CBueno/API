from fastapi import UploadFile, APIRouter, Depends, File
from controllers.auth import getCurrentUser
from fastapi.responses import JSONResponse
from models.flashCardModel import processFlashcards
import fitz  # PyMuPDF
from connection import prismaConnection as db
import tempfile
import os
import easyocr
import math


router = APIRouter(
    prefix='/logic',
    tags=['logic']
)



@router.post('/flashcards')
async def handle_flashcard_pdf(
    current_user: dict = Depends(getCurrentUser),
    pdf: UploadFile = File(...)
):
    pdf_filename = pdf.filename  # pega o nome do arquivo enviado
    
    if current_user is None:
        return JSONResponse(content={"success": False, "detail": "Usuário não autenticado"}, status_code=401)
    
    if pdf is None or pdf.content_type != "application/pdf":
        return JSONResponse(content={"success": False, "detail": "Arquivo inválido, apenas PDF é aceito"}, status_code=400)

    fileSizeInBytes = pdf.size  # Tamanho em bytes
    bytesPerToken = 409600
    tokens = math.ceil(fileSizeInBytes / bytesPerToken)

    print(f"Arquivo: {pdf_filename}, Tamanho: {fileSizeInBytes} bytes, Tokens necessários: {tokens}")

    verifyTokens = await db.prisma.user.find_unique(
        where={'id': current_user["id"]}
    )
    
    print(f"Usuário encontrado: {verifyTokens is not None}, Tokens disponíveis: {verifyTokens.tokens if verifyTokens else 'N/A'}")
    
    if not verifyTokens or verifyTokens.tokens < tokens:
        return JSONResponse(content={
            "success": False, 
            "detail": f"Tokens insuficientes. Necessário: {tokens}, Disponível: {verifyTokens.tokens if verifyTokens else 0}"
        }, status_code=400)
    
    
    ocr = easyocr.Reader(['pt'], gpu=False)

    # Ler o conteúdo do arquivo
    content = await pdf.read()
        
    # Criar arquivo temporário
    with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_file:
        temp_file.write(content)
        temp_file_path = temp_file.name
    
    try:
        doc = fitz.open(temp_file_path)
        full_text = ""

        for page in doc:
            text = page.get_text()  # Tenta extrair texto digital
            if text.strip():  # Página digital
                full_text += text + "\n\n"
            else:  # Página escaneada
                pix = page.get_pixmap()
                img_path = temp_file_path.replace(".pdf", f"_page_{page.number}.png")
                pix.save(img_path)

                # OCR com EasyOCR
                ocr_result = ocr.readtext(img_path, detail=0)  # detail=0 retorna apenas o texto
                full_text += "\n".join(ocr_result) + "\n"
                
                os.remove(img_path)
        
        # Exportar para markdown
        markdown_content = f"# Conteúdo do PDF\n\n{full_text}"
        
        # Salvar markdown em arquivo
        # filename = f"flashcard_{current_user['id']}_{pdf.filename.replace('.pdf', '')}.md"
        # filepath = os.path.join("outputs", filename)
        # os.makedirs("outputs", exist_ok=True)
        # with open(filepath, "w", encoding="utf-8") as f:
        #     f.write(markdown_content)

        pdf_record = await db.prisma.pdf.create(
            data={
                "name": pdf_filename,
                "userId": current_user["id"],
                "extracted_text": markdown_content
            }
        )

        # Remover tokens do usuário
        try:
            await db.prisma.user.update(
                where={'id': current_user["id"]},
                data={'tokens': verifyTokens.tokens - tokens}
            )
            print(f"Tokens atualizados: {verifyTokens.tokens} -> {verifyTokens.tokens - tokens}")
        except Exception as e:
            print(f"Erro ao atualizar tokens: {str(e)}")
            raise e

        final = await processFlashcards(markdown_content, current_user)

        # Prepara os dados para create_many
        flashcards_data = [
            {
                "pdfId": pdf_record.id,
                "front": flash["front"],
                "back": flash["back"]
            }
            for flash in final
        ]

        # Cria todos os flashcards de uma vez
        await db.prisma.flashcard.create_many(
            data=flashcards_data
        )
        
        return JSONResponse(content={
            "success": True,
            "detail": "PDF processado com sucesso",
            # "flashcards": final,
            "user": current_user
        }, status_code=200)
            
    except Exception as e:
        return JSONResponse(content={
            "success": False, 
            "detail": f"Erro ao processar PDF: {str(e)}"
        }, status_code=500)
            
    finally:
        # Limpar arquivo temporário
        if os.path.exists(temp_file_path):
            os.unlink(temp_file_path)
    