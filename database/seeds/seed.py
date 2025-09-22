import asyncio
import os
from prisma import Prisma
import bcrypt
from dotenv import load_dotenv

# Carrega variáveis de ambiente do .env
load_dotenv()

async def main():
    db = Prisma()
    await db.connect()

    email = os.getenv("ADMIN_EMAIL")
    raw_password = os.getenv("ADMIN_PASSWORD")

    if not email or not raw_password:
        print("⚠️  ADMIN_EMAIL ou ADMIN_PASSWORD não definidos no .env")
        await db.disconnect()
        return

    hashed_password = bcrypt.hashpw(raw_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    # Verifica se o usuário já existe
    existing_user = await db.user.find_unique(where={"email": email})
    if existing_user:
        print(f"Usuário {email} já existe. ✅")
    else:
        user = await db.user.create(
            data={
                "email": email,
                "password": hashed_password,
                "role": "admin",
                "is_verified": True,
            }
        )
        print(f"Usuário admin criado: {user.email} ✅")

    await db.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
