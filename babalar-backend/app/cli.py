"""
Admin setup CLI:
  python -m app.cli setup --email admin@example.com --username admin --password SECRET
"""
import argparse
import asyncio
import secrets
import sys

from sqlalchemy import text

from app.auth import hash_password
from app.database import engine, SessionLocal
from app.models.models import AdminConfig, InviteCode, User


async def setup(email: str, username: str, password: str):
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

    async with SessionLocal() as db:
        defaults = {
            "user_daily_limit": "5",
            "total_daily_limit": "5000",
            "rag_top_k": "10",
            "ingestion_lookback_days": "30",
        }
        for key, value in defaults.items():
            existing = await db.get(AdminConfig, key)
            if not existing:
                db.add(AdminConfig(key=key, value=value))

        admin = User(
            email=email,
            username=username,
            password_hash=hash_password(password),
            is_admin=True,
        )
        db.add(admin)

        code = secrets.token_urlsafe(8)
        db.add(InviteCode(code=code, max_uses=50))

        await db.commit()
        print(f"Setup tamamlandı.")
        print(f"İlk davet kodu: {code}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd")
    p = sub.add_parser("setup")
    p.add_argument("--email", required=True)
    p.add_argument("--username", required=True)
    p.add_argument("--password", required=True)
    args = parser.parse_args()

    if args.cmd == "setup":
        asyncio.run(setup(args.email, args.username, args.password))
