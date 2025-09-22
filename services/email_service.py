from fastapi_mail import FastMail, MessageSchema, ConnectionConfig
from dotenv import load_dotenv
import os
import random
import string

load_dotenv()

# Configuração do FastAPI-Mail
conf = ConnectionConfig(
    MAIL_USERNAME=os.getenv("MAIL_USERNAME"),
    MAIL_PASSWORD=os.getenv("MAIL_PASSWORD"),
    MAIL_FROM=os.getenv("MAIL_FROM"),
    MAIL_PORT=int(os.getenv("MAIL_PORT", 587)),
    MAIL_SERVER=os.getenv("MAIL_SERVER"),
    MAIL_STARTTLS=True,
    MAIL_SSL_TLS=False,
    USE_CREDENTIALS=True,
    VALIDATE_CERTS=True
)

class EmailService:
    def __init__(self):
        self.fastmail = FastMail(conf)
    
    def generate_otp(self, length: int = 6) -> str:
        """Gera um código OTP numérico"""
        return ''.join(random.choices(string.digits, k=length))
    
    async def send_otp_email(self, email: str, otp_code: str) -> bool:
        """Envia email com código OTP"""
        try:
            message = MessageSchema(
                subject="Código de Verificação - Flashcard App",
                recipients=[email],
                body=f"""
                <html>
                <body>
                    <h2>Verificação de Email</h2>
                    <p>Olá!</p>
                    <p>Seu código de verificação é: <strong style="font-size: 24px; color: #007bff;">{otp_code}</strong></p>
                    <p>Este código expira em 5 minutos.</p>
                    <p>Se você não solicitou este código, ignore este email.</p>
                    <br>
                    <p>Equipe FlashIdea</p>
                </body>
                </html>
                """,
                subtype="html"
            )
            
            await self.fastmail.send_message(message)
            return True
        except Exception as e:
            print(f"Erro ao enviar email: {e}")
            return False

# Instância global do serviço de email
email_service = EmailService()
