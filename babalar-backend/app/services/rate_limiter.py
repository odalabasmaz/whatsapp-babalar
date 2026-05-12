import uuid
from datetime import date, timezone

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import AdminConfig, DailyTotalUsage, UserDailyUsage


async def _get_config(db: AsyncSession, key: str, default: int) -> int:
    result = await db.execute(select(AdminConfig).where(AdminConfig.key == key))
    row = result.scalar_one_or_none()
    return int(row.value) if row else default


async def check_and_increment(db: AsyncSession, user_id: uuid.UUID, limit_override: int | None = None) -> tuple[bool, str]:
    today = date.today()

    user_limit = limit_override if limit_override is not None else await _get_config(db, "user_daily_limit", 5)
    total_limit = await _get_config(db, "total_daily_limit", 5000)

    # Toplam günlük kullanım
    total_row = await db.execute(select(DailyTotalUsage).where(DailyTotalUsage.usage_date == today))
    total = total_row.scalar_one_or_none()
    if total and total.count >= total_limit:
        return False, f"Günlük toplam limit ({total_limit}) aşıldı. Yarın tekrar dene."

    # Kullanıcı günlük kullanım
    user_row = await db.execute(
        select(UserDailyUsage).where(UserDailyUsage.user_id == user_id, UserDailyUsage.usage_date == today)
    )
    usage = user_row.scalar_one_or_none()
    if usage and usage.count >= user_limit:
        return False, f"Günlük kişisel limitin ({user_limit} soru) doldu. Yarın tekrar dene."

    # Sayaçları artır (upsert)
    await db.execute(
        text("""
            INSERT INTO user_daily_usage (user_id, usage_date, count)
            VALUES (:uid, :d, 1)
            ON CONFLICT (user_id, usage_date) DO UPDATE SET count = user_daily_usage.count + 1
        """),
        {"uid": str(user_id), "d": today},
    )
    await db.execute(
        text("""
            INSERT INTO daily_total_usage (usage_date, count)
            VALUES (:d, 1)
            ON CONFLICT (usage_date) DO UPDATE SET count = daily_total_usage.count + 1
        """),
        {"d": today},
    )
    await db.commit()
    return True, ""
