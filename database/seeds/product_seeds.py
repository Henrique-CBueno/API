import asyncio
from prisma import Prisma

async def main():
    db = Prisma()
    await db.connect()

    products = [
        {
            "name": "Básico",
            "price": 14.99,
            "tokens": 15
        },
        {
            "name": "Anual",
            "price": 119.90,
            "tokens": 365,
        },
        {
            "name": "Mensal",
            "price": 34.99,
            "tokens": 60
        }
    ]


    for p in products:
        existing = await db.product.find_first(where={"name": p["name"]})
        if existing:
            print(f"Produto {p['name']} já existe.")
        else:
            await db.product.create(data=p)
            print(f"Produto {p['name']} criado ✅")

    await db.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
