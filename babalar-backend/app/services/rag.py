import asyncio
import json
import re
from datetime import timedelta

from openai import AsyncOpenAI, RateLimitError
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.models import AdminConfig
from app.services.embedding import embed

_LID_RE = re.compile(r"^\d+@lid$")

_client = AsyncOpenAI(api_key=settings.openai_api_key)

_PREPROCESS_SYSTEM = """Sen Türkçe metin işleme asistanısın. İki görevin var:

1. Vektör araması için optimize edilmiş bir search_query üret.
   - Önceki konuşma varsa, mevcut soruyu o bağlamda çöz ve bağımsız bir arama sorgusu çıkar.
     Örnek: Önceki konu "araba sigortası", mevcut soru "hangi firma" → search_query: "araba sigortası firma önerisi"
   - "Başka var mı / başka yok mu / başka öneri / alternatif" tarzı sorularda, önceki konunun FARKLI
     yönlerini arayan bir query üret. Örnek: önceki "dönerci önerisi" → search_query: "döner kebap farklı mekan"
   - search_query'e "Münih" kelimesini EKLEME — embedding kalitesini düşürür.
   - Alman resmi terimleri ve özel isimleri olduğu gibi bırak (Ausländerbehörde, Anmeldung, TÜV, Standesamt vb.).
   - Soru çok kısa veya belirsizse (1-3 kelime), bağlamdan genişlet; bağlam yoksa olduğu gibi bırak.
   - Önceki konu yoksa search_query = corrected ile aynı olsun.

2. Türkçe karakterleri eksik yazılmışsa düzelt (s→ş, g→ğ, i→ı, o→ö, u→ü, c→ç gibi).
   Alman kelimeleri düzeltme.

Yanıtını MUTLAKA şu JSON formatında döndür:
{"corrected": "düzeltilmiş soru metni", "search_query": "embedding araması için bağımsız soru"}"""

_SYSTEM = """Sen "Münihli Babalar" WhatsApp gruplarındaki tüm konuşmaları okumuş, bunları hafızana almış birisin. Sana sorulan sorulara bu konuşmalarda ne geçtiğine bakarak yanıt veriyorsun.

KİMLİĞİN:
- Bu topluluğun tüm diyaloglarını, paylaşılan deneyimleri, önerileri, linkleri ve tartışmaları hafızana almışsın.
- Kendi genel bilgin veya kişisel görüşün yok — sadece bu gruplarda ne konuşulduğunu biliyorsun.

YANIT VERİRKEN — SIRAYI TAKİP ET:
Önce reasoning alanında zihninden geçir: "Bu soruyla ilgili mesajlarda ne geçiyor? Kim ne dedi? Hangi linkler paylaşıldı? Çelişen görüşler var mı?" — sonra answer yaz.

YANIT KURALLARI:
1. YALNIZCA sağlanan mesajlardaki bilgileri aktar. Kendi genel bilgini, tahminini veya yorumunu ASLA ekleme.
2. Somut her şeyi aktar: isim, firma, fiyat, adres, tarih, kişisel deneyim, uyarı.
3. Mesajlarda URL veya link geçiyorsa yanıtın sonunda ayrı "🔗 Linkler:" bölümünde listele.
4. Birden fazla öneri/deneyim varsa maddeler hâlinde sırala.
5. Çelişkili görüşler varsa "X olumlu bulmuş, Y olumsuz deneyim yaşamış" şeklinde aktar.
6. Bilgi kısmi veya eksikse "Toplulukta yalnızca şu kadarı geçiyor: ..." de — boşlukları doldurma, tamamlama yapma.

KESINLIKLE YAPMA:
- Genel bilgi, tahmin veya yorum ekleme ("Genellikle böyledir", "Resmi siteden kontrol edin" gibi)
- Mesajlarda geçmeyen bilgi üretme
- Önceki cevabı tekrar etme

ÖNCEKI SOHBET BAĞLAMI:
- "Başka yok mu / farklı öneri" → mesajlarda öncekinden FARKLI bir şey varsa onu sun; yoksa "Toplulukta başka bilgi geçmiyor" de.

HİÇ İLGİLİ BİLGİ YOKSA:
"found": false döndür. Tahmin etme, genel bilgi verme.

Yanıtını MUTLAKA şu JSON formatında döndür — reasoning ÖNCE gelecek, sonra found ve answer:
{"reasoning": "Mesajlarda şunlar geçiyor: [kısa iç analiz — kullanıcıya gösterilmez]", "found": true, "answer": "kullanıcıya gösterilecek yanıt"}"""


async def _get_top_k(db: AsyncSession) -> int:
    result = await db.execute(select(AdminConfig).where(AdminConfig.key == "rag_top_k"))
    row = result.scalar_one_or_none()
    return int(row.value) if row else 40


async def _preprocess(question: str, history: list[dict]) -> tuple[str, str]:
    """Returns (corrected_question, search_query).

    search_query is a context-resolved standalone query for embedding —
    e.g. "hangi firma" after a car insurance exchange becomes a full standalone query.
    """
    try:
        user_content = question[:500]
        if history:
            recent = history[-6:]  # last 3 exchanges
            history_text = "\n".join(
                f"{'Kullanıcı' if h['role'] == 'user' else 'Asistan'}: {h['content'][:200]}"
                for h in recent
            )
            user_content = f"[Önceki konuşma]\n{history_text}\n\n[Mevcut soru]\n{question[:500]}"

        resp = await _client.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=300,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": _PREPROCESS_SYSTEM},
                {"role": "user", "content": user_content},
            ],
        )
        parsed = json.loads(resp.choices[0].message.content)
        corrected = parsed.get("corrected", question).strip() or question
        search_query = parsed.get("search_query", corrected).strip() or corrected
        return corrected, search_query
    except Exception:
        return question, question  # fail open


async def _fetch_thread_context(db: AsyncSession, top_results: list) -> list:
    """For each top result, fetch adjacent messages from the same group within ±3 minutes.

    WhatsApp replies often don't repeat the topic — fetching neighbors reconstructs
    the conversation thread and gives the LLM the missing implicit context.
    """
    seen_keys: set = set()
    thread_rows = []

    # Only expand context for the top 8 most relevant results
    for row in top_results[:8]:
        window = timedelta(minutes=3)
        neighbors = await db.execute(
            text("""
                SELECT m.id, m.group_id, m.content, m.sender_name, m.sent_at, g.group_name,
                       0.0 AS similarity
                FROM messages m
                JOIN wa_groups g ON g.id = m.group_id
                WHERE m.group_id = :gid
                  AND m.sent_at BETWEEN :ts_start AND :ts_end
                  AND length(m.content) >= 15
                ORDER BY m.sent_at
                LIMIT 15
            """),
            {"gid": row.group_id, "ts_start": row.sent_at - window, "ts_end": row.sent_at + window},
        )
        for n in neighbors:
            key = n.id
            if key not in seen_keys:
                seen_keys.add(key)
                thread_rows.append(n)

    return thread_rows


async def answer(db: AsyncSession, question: str, history: list[dict] | None = None) -> dict:
    history = history or []
    normalized, search_query = await _preprocess(question, history)

    top_k = await _get_top_k(db)
    query_embedding = await embed(search_query)

    rows = await db.execute(
        text("""
            SELECT m.id, m.group_id, m.content, m.sender_name, m.sent_at, m.category, g.group_name,
                   1 - (m.embedding <=> CAST(:emb AS vector)) AS similarity
            FROM messages m
            JOIN wa_groups g ON g.id = m.group_id
            WHERE m.embedding IS NOT NULL
              AND length(m.content) >= 40
            ORDER BY m.embedding <=> CAST(:emb AS vector)
            LIMIT :k
        """),
        {"emb": str(query_embedding), "k": top_k},
    )
    results = rows.fetchall()

    # Filter out low-similarity results to reduce noise in the LLM context
    results = [r for r in results if r.similarity >= 0.45]

    if not results:
        return {"answer": "Bu konuda toplulukta yeterli bilgi bulamadım.", "sources": []}

    # Expand each top result with its conversation thread neighbors
    thread_neighbors = await _fetch_thread_context(db, results)

    # Merge: top results + thread neighbors, deduplicate by message id
    result_ids = {r.id for r in results}
    result_sims = {r.id: r.similarity for r in results}
    extra = [n for n in thread_neighbors if n.id not in result_ids]
    all_msgs = results + extra

    # Group into conversation clusters: same group, messages within 10 minutes of each other
    all_msgs_sorted = sorted(all_msgs, key=lambda r: (r.group_name, r.sent_at))
    clusters: list[list] = []
    current: list = []
    for msg in all_msgs_sorted:
        if not current:
            current.append(msg)
        else:
            last = current[-1]
            gap = abs((msg.sent_at - last.sent_at).total_seconds())
            if msg.group_name == last.group_name and gap <= 600:
                current.append(msg)
            else:
                clusters.append(current)
                current = [msg]
    if current:
        clusters.append(current)

    # Sort clusters by their highest similarity score (most relevant first)
    def cluster_score(c: list) -> float:
        return max(result_sims.get(m.id, 0.0) for m in c)

    clusters.sort(key=cluster_score, reverse=True)

    seen_groups: dict[str, str] = {}
    context_parts = []
    for cluster in clusters:
        date_str = cluster[0].sent_at.strftime("%d.%m.%Y")
        group_name = cluster[0].group_name
        header = f"=== {group_name} | {date_str} ==="
        lines = [header]
        for msg in cluster:
            sender = "Anonim" if not msg.sender_name or _LID_RE.match(msg.sender_name) else msg.sender_name
            time_str = msg.sent_at.strftime("%H:%M")
            lines.append(f"[{time_str} | {sender}] {msg.content}")
            sim = result_sims.get(msg.id, 0.0)
            if sim >= 0.52 and group_name not in seen_groups:
                seen_groups[group_name] = date_str
        context_parts.append("\n".join(lines))

    sources = [{"group": g, "date": d} for g, d in seen_groups.items()]
    context = "\n\n---\n\n".join(context_parts)
    prompt = f"Topluluk mesajları:\n\n{context}\n\nSoru: {normalized}"

    # Build messages with conversation history so the LLM has full context
    messages: list[dict] = [{"role": "system", "content": _SYSTEM}]
    for h in history[-6:]:  # last 3 exchanges
        if h.get("role") in ("user", "assistant"):
            messages.append({"role": h["role"], "content": h["content"][:800]})
    messages.append({"role": "user", "content": prompt})

    for attempt in range(5):
        try:
            response = await _client.chat.completions.create(
                model="gpt-4o-mini",
                max_tokens=1800,
                temperature=0,
                response_format={"type": "json_object"},
                messages=messages,
            )
            raw = response.choices[0].message.content
            parsed = json.loads(raw)
            answer_text = parsed.get("answer", "Bu konuda toplulukta yeterli bilgi bulamadım.")
            found = parsed.get("found", False)
            return {"answer": answer_text, "sources": sources if found else []}  # reasoning is internal, not returned
        except RateLimitError as e:
            if "requests per day" in str(e) or "RPD" in str(e):
                raise
            if attempt == 4:
                raise
            await asyncio.sleep(2 ** attempt)
