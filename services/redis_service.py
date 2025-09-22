import redis
import json
from datetime import timedelta
from dotenv import load_dotenv
import os

load_dotenv()

class RedisService:
    def __init__(self):
        self.redis_client = redis.Redis(
            host=os.getenv("REDIS_HOST", "localhost"),
            port=int(os.getenv("REDIS_PORT", 6379)),
            db=int(os.getenv("REDIS_DB", 0)),
            decode_responses=True
        )
    
    def store_otp(self, email: str, otp_code: str, user_id: int, expiration_minutes: int = 5) -> bool:
        """Armazena OTP no Redis com expiração"""
        try:
            otp_data = {
                "code": otp_code,
                "user_id": user_id,
                "email": email
            }
            
            key = f"otp:{email}"
            self.redis_client.setex(
                key, 
                timedelta(minutes=expiration_minutes), 
                json.dumps(otp_data)
            )
            return True
        except Exception as e:
            print(f"Erro ao armazenar OTP no Redis: {e}")
            return False
    
    def get_otp(self, email: str) -> dict:
        """Recupera dados do OTP do Redis"""
        try:
            key = f"otp:{email}"
            otp_data = self.redis_client.get(key)
            
            if otp_data:
                return json.loads(otp_data)
            return None
        except Exception as e:
            print(f"Erro ao recuperar OTP do Redis: {e}")
            return None
    
    def verify_otp(self, email: str, otp_code: str) -> dict:
        """Verifica se o OTP está correto e retorna os dados do usuário"""
        try:
            otp_data = self.get_otp(email)
            
            if not otp_data:
                return {"valid": False, "message": "OTP não encontrado ou expirado"}
            
            if otp_data["code"] != otp_code:
                return {"valid": False, "message": "Código OTP incorreto"}
            
            # Remove o OTP após verificação bem-sucedida
            self.delete_otp(email)
            
            return {
                "valid": True, 
                "user_id": otp_data["user_id"],
                "email": otp_data["email"]
            }
        except Exception as e:
            print(f"Erro ao verificar OTP: {e}")
            return {"valid": False, "message": "Erro interno do servidor"}
    
    def delete_otp(self, email: str) -> bool:
        """Remove OTP do Redis"""
        try:
            key = f"otp:{email}"
            self.redis_client.delete(key)
            return True
        except Exception as e:
            print(f"Erro ao deletar OTP do Redis: {e}")
            return False
    
    def is_otp_valid(self, email: str) -> bool:
        """Verifica se existe um OTP válido para o email"""
        try:
            key = f"otp:{email}"
            return self.redis_client.exists(key) > 0
        except Exception as e:
            print(f"Erro ao verificar validade do OTP: {e}")
            return False

    def enqueue_task(self, queue_name: str, task: dict) -> bool:
        """Adiciona uma tarefa na fila Redis"""
        try:
            self.redis_client.rpush(queue_name, json.dumps(task))
            return True
        except Exception as e:
            print(f"Erro ao enfileirar tarefa: {e}")
            return False

    def dequeue_task(self, queue_name: str) -> dict | None:
        """Remove e retorna a próxima tarefa da fila (FIFO)"""
        try:
            task_data = self.redis_client.lpop(queue_name)
            if task_data:
                return json.loads(task_data)
            return None
        except Exception as e:
            print(f"Erro ao desenfileirar tarefa: {e}")
            return None

# Instância global do serviço Redis
redis_service = RedisService()
