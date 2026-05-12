# Babalar — Mimari ve Deployment Rehberi

## Proje Özeti

**Babalar**, bir WhatsApp topluluğundaki grup konuşmalarını indeksleyen, kategorize eden ve kullanıcıların Türkçe soru sorabileceği bir chatbot uygulamasıdır. Topluluk mesajları her gece otomatik çekilir, vektör veritabanına kaydedilir ve kullanıcı sorularına RAG (Retrieval-Augmented Generation) yöntemiyle Claude AI kullanarak yanıt verilir.

**Domain**: `your-domain.com`
**Erişim**: Sadece Almanya IP adresleri (CloudFront Geo-Restriction)

---

## Sistem Mimarisi

```
Internet (Almanya IP)
        │
        ▼
  [CloudFront]  ← Geo-Restriction: sadece DE
  /          \
[S3]        [ALB]
(Frontend)    │
              │
        [EC2 t4g.small]
        ┌────┴────────────────┐
        │  babalar-backend    │  (Docker, Python/FastAPI, :8000)
        │  babalar-ingestion  │  (Docker, Node.js, cron her gece 02:00)
        └────────────────────-┘
              │
        [RDS PostgreSQL]
        db.t4g.micro + pgvector
        (Private Subnet)
```

---

## Bileşenler

### babalar-backend (Python 3.12 + FastAPI)
- REST API: auth, chat, admin, ingest
- RAG engine: soru → embedding → pgvector similarity → GPT-4o-mini
- Mesaj kategorizasyonu (GPT-4o-mini)
- JWT tabanlı auth + invite code sistemi
- Rate limiting (PostgreSQL tabanlı, Redis yok)
- Port: 8000

### babalar-ingestion (Node.js)
- whatsapp-web.js ile WhatsApp Web'e bağlanır (sadece okuma)
- Her gece 02:00'de (UTC) çalışır
- Grup başına `last_ingested_at` takibi yapar, sadece yeni mesajları alır
- İlk çalıştırmada son 30 günü işler
- Mesajları backend'e POST `/api/ingest/messages` ile gönderir
- whatsapp-web.js session'ını Docker volume'da persist eder

### babalar-frontend (React + Vite + TypeScript + Tailwind)
- Login / Kayıt (davet kodu zorunlu)
- Chat arayüzü (soru → yanıt + kaynak mesajlar)
- Kategori bazlı browse
- Admin paneli (rate limit config, invite code yönetimi)
- S3'te static host, CloudFront üzerinden servis

### infrastructure (AWS CDK Python)
- `NetworkStack`: VPC, public/private subnet, ALB
- `DatabaseStack`: RDS PostgreSQL t4g.micro + pgvector, private subnet
- `ComputeStack`: EC2 t4g.small, Security Group, IAM role, user data
- `FrontendStack`: S3 bucket, CloudFront distribution, Geo-Restriction (DE)

---

## Veritabanı Şeması

```sql
-- Kullanıcılar
CREATE TABLE users (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email       VARCHAR(255) UNIQUE NOT NULL,
    username    VARCHAR(100) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    invite_code VARCHAR(50),
    is_admin    BOOLEAN DEFAULT FALSE,
    is_active   BOOLEAN DEFAULT TRUE,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Davet Kodları
CREATE TABLE invite_codes (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code        VARCHAR(50) UNIQUE NOT NULL,
    max_uses    INTEGER DEFAULT 10,
    use_count   INTEGER DEFAULT 0,
    is_active   BOOLEAN DEFAULT TRUE,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- WhatsApp Grupları
CREATE TABLE wa_groups (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    wa_group_id     VARCHAR(255) UNIQUE NOT NULL,
    group_name      VARCHAR(255) NOT NULL,
    is_active       BOOLEAN DEFAULT TRUE,
    last_ingested_at TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Mesajlar (vektör dahil)
CREATE TABLE messages (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    group_id    UUID REFERENCES wa_groups(id) ON DELETE CASCADE,
    sender_name VARCHAR(255),
    content     TEXT NOT NULL,
    sent_at     TIMESTAMPTZ NOT NULL,
    ingested_at TIMESTAMPTZ DEFAULT NOW(),
    category    VARCHAR(100),
    embedding   vector(1536),
    CONSTRAINT content_not_empty CHECK (length(trim(content)) > 0)
);
CREATE INDEX ON messages USING hnsw (embedding vector_cosine_ops);
CREATE INDEX ON messages (category);
CREATE INDEX ON messages (sent_at DESC);

-- Kullanıcı Günlük Kullanım
CREATE TABLE user_daily_usage (
    user_id     UUID REFERENCES users(id) ON DELETE CASCADE,
    usage_date  DATE NOT NULL DEFAULT CURRENT_DATE,
    count       INTEGER DEFAULT 0,
    PRIMARY KEY (user_id, usage_date)
);

-- Toplam Günlük Kullanım
CREATE TABLE daily_total_usage (
    usage_date  DATE PRIMARY KEY DEFAULT CURRENT_DATE,
    count       INTEGER DEFAULT 0
);

-- Admin Konfigürasyon
CREATE TABLE admin_config (
    key         VARCHAR(100) PRIMARY KEY,
    value       TEXT NOT NULL,
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);
-- Başlangıç değerleri:
-- ('user_daily_limit', '5')       → kişi başı günlük soru limiti
-- ('total_daily_limit', '5000')   → günlük toplam soru limiti
-- ('rag_top_k', '10')             → RAG'da kaç mesaj context olarak alınsın
-- ('ingestion_lookback_days', '30') → ilk ingest'te kaç gün geriye gidilsin
```

---

## API Endpoints

### Auth
| Method | Path | Açıklama |
|--------|------|----------|
| POST | `/api/auth/register` | Kayıt (email, username, password, invite_code) |
| POST | `/api/auth/login` | Giriş → access + refresh token |
| POST | `/api/auth/refresh` | Access token yenile |
| POST | `/api/auth/logout` | Refresh token iptal |

### Chat
| Method | Path | Açıklama |
|--------|------|----------|
| POST | `/api/chat/ask` | Soru sor → RAG yanıt |
| GET | `/api/chat/history` | Kullanıcının soru geçmişi |
| GET | `/api/chat/categories` | Mevcut kategoriler |
| GET | `/api/chat/search` | Mesajlarda arama |

### Admin (admin rolü gerektirir)
| Method | Path | Açıklama |
|--------|------|----------|
| GET | `/api/admin/config` | Tüm config değerlerini getir |
| PUT | `/api/admin/config/{key}` | Config değeri güncelle |
| GET | `/api/admin/invite-codes` | Davet kodlarını listele |
| POST | `/api/admin/invite-codes` | Yeni davet kodu oluştur |
| DELETE | `/api/admin/invite-codes/{id}` | Davet kodu sil/deaktif et |
| GET | `/api/admin/users` | Kullanıcıları listele |
| GET | `/api/admin/stats` | Kullanım istatistikleri |
| GET | `/api/admin/groups` | WhatsApp gruplarını listele |

### Ingest (internal, ingestion servisi kullanır)
| Method | Path | Açıklama |
|--------|------|----------|
| POST | `/api/ingest/messages` | Mesajları batch olarak ekle |
| GET | `/api/ingest/groups` | Grup listesi ve last_ingested_at |
| POST | `/api/ingest/groups` | Yeni grup kaydet veya güncelle |

---

## RAG Akışı

```
Kullanıcı sorusu
    │
    ▼
Rate limit kontrol
    │
    ▼
Soruyu embedding'e çevir (OpenAI text-embedding-3-small)
    │
    ▼
pgvector'de cosine similarity search (top-K mesaj, default 10)
    │
    ▼
GPT-4o-mini'ye prompt gönder:
  - System: "Sen Babalar topluluğunun Türkçe asistanısın..."
  - Context: top-K mesaj (grup adı, tarih, içerik)
  - User: soru
    │
    ▼
Yanıt + kaynak mesajlar kullanıcıya döner
    │
    ▼
Rate limit sayacı güncelle
```

---

## İngestion Akışı

```
Her gece 02:00 UTC (node-cron)
    │
    ▼
whatsapp-web.js QR oturumu kontrol et (persist edilmiş session)
    │
    ▼
Her aktif grup için:
  - last_ingested_at'dan bu yana gelen mesajları al
  - İlk çalıştırma: son 30 gün
    │
    ▼
Backend /api/ingest/messages POST (batch, 100'lü paketler)
    │
    ▼
Backend her mesaj için:
  1. GPT-4o-mini → kategori belirle
  2. OpenAI text-embedding-3-small → embedding oluştur
  3. PostgreSQL'e kaydet
    │
    ▼
wa_groups.last_ingested_at güncelle
```

---

## AWS Infrastructure

### VPC
- 2 Availability Zone: eu-central-1a, eu-central-1b
- Public subnet: EC2, ALB
- Private subnet: RDS
- Internet Gateway → public subnet
- **NAT Gateway yok** (EC2 public subnet'te, security group ile kısıtlanmış)

### EC2
- Instance: `t4g.small` (ARM Graviton2, 2 vCPU, 2 GB RAM)
- AMI: Amazon Linux 2023 ARM64
- Security Group: sadece ALB'den 8000, SSH için kendi IP'nden 22
- IAM Role: Secrets Manager okuma, CloudWatch Logs yazma
- User Data: Docker + Docker Compose kurulumu
- EBS: 20 GB gp3

### RDS
- Instance: `db.t4g.micro` (Graviton2, 1 GB RAM)
- Engine: PostgreSQL 16 + pgvector extension
- Storage: 20 GB gp3
- Subnet: Private
- Security Group: sadece EC2'den 5432
- Multi-AZ: Hayır (maliyet odaklı, availability kritik değil)
- Backup: 7 gün retention

### CloudFront
- Origin 1: S3 (React frontend)
- Origin 2: ALB (API — `/api/*` path)
- Geo-Restriction: Whitelist → `DE`
- Price Class: 100 (sadece US/EU edge, en ucuz)
- SSL: ACM sertifikası (us-east-1'de — CloudFront zorunluluğu)

### ALB
- Target: EC2 (port 8000)
- Health check: `GET /health`
- ASG: desired=1, min=1, max=1 (ileride 3'e çıkarılabilir)
- HTTPS listener: 443 → EC2:8000
- HTTP listener: 80 → 443 redirect

### Secrets Manager
- `babalar/db-password`: RDS şifresi
- `babalar/claude-api-key`: Anthropic API key
- `babalar/openai-api-key`: OpenAI embedding API key
- `babalar/jwt-secret`: JWT imzalama secret
- `babalar/ingest-api-key`: Ingestion servisi iç API key

---

## Maliyet Özeti (Aylık, eu-central-1)

| Kaynak | Açıklama | Tahmini |
|--------|----------|---------|
| EC2 t4g.small | On-demand | ~$12 |
| RDS db.t4g.micro | Single-AZ | ~$13 |
| CloudFront | Price Class 100, minimal traffic | ~$3 |
| S3 | Static hosting | <$1 |
| Route53 | Hosted zone + queries | ~$1 |
| Secrets Manager | 5 secret | ~$2 |
| CloudWatch Logs | 7 gün retention | ~$1 |
| Claude Haiku API | 5000 soru/gün max | ~$10-20 |
| OpenAI Embeddings | text-embedding-3-small | ~$2 |
| **Toplam** | | **~$45-55/ay** |

---

## Geliştirme Ortamı Kurulumu

### Gereksinimler
- Docker + Docker Compose
- Node.js 20+
- Python 3.12+
- AWS CLI + CDK CLI

### Local Başlatma

```bash
# 1. Environment değişkenlerini kopyala
cp .env.example .env
# .env dosyasını düzenle (API key'leri ekle)

# 2. Tüm servisleri başlat
docker compose up -d

# 3. Migration çalıştır (ilk kez)
docker compose exec backend alembic upgrade head

# 4. Admin kullanıcısı + ilk invite kodu oluştur
docker compose exec backend python -m app.cli setup

# 5. WhatsApp QR kod tara (ingestion servisi)
docker compose logs -f ingestion
# Terminalde QR kod görünecek, WhatsApp ile tara
```

### Servis URL'leri (local)
- Backend API: http://localhost:8000
- API Docs: http://localhost:8000/docs
- Frontend: http://localhost:5173
- PostgreSQL: localhost:5432

---

## Production Deployment

### İlk Kurulum

```bash
# 1. AWS CDK bootstrap (ilk kez)
cd infrastructure
pip install -r requirements.txt
cdk bootstrap aws://ACCOUNT_ID/eu-central-1

# 2. Secrets'leri manuel oluştur (CDK deploy öncesi)
aws secretsmanager create-secret --name babalar/db-password --secret-string "GUCLU_SIFRE"
aws secretsmanager create-secret --name babalar/claude-api-key --secret-string "sk-ant-..."
aws secretsmanager create-secret --name babalar/openai-api-key --secret-string "sk-..."
aws secretsmanager create-secret --name babalar/jwt-secret --secret-string "$(openssl rand -hex 32)"
aws secretsmanager create-secret --name babalar/ingest-api-key --secret-string "$(openssl rand -hex 32)"

# 3. CDK deploy
cdk deploy --all

# 4. EC2'ya bağlan ve uygulamayı başlat
ssh ec2-user@EC2_IP
cd /app
git clone https://github.com/YOUR_ORG/babalar.git .
docker compose -f docker-compose.prod.yml up -d

# 5. Migration
docker compose exec backend alembic upgrade head

# 6. Admin setup
docker compose exec backend python -m app.cli setup

# 7. DNS (Route53 veya domain sağlayıcınızın DNS paneli)
# your-domain.com → CloudFront distribution domain
```

### Güncelleme (Sonraki Deploylar)

```bash
ssh ec2-user@EC2_IP
cd /app
git pull
docker compose -f docker-compose.prod.yml up -d --build
docker compose exec backend alembic upgrade head
```

---

## Konfigürasyon Referansı

### Environment Variables

| Değişken | Açıklama | Örnek |
|----------|----------|-------|
| `DATABASE_URL` | PostgreSQL connection string | `postgresql+asyncpg://user:pass@host/db` |
| `CLAUDE_API_KEY` | Anthropic API key | `sk-ant-...` |
| `OPENAI_API_KEY` | OpenAI embedding API key | `sk-...` |
| `JWT_SECRET` | JWT imzalama secret | 32+ char random string |
| `JWT_ACCESS_TTL_MINUTES` | Access token süresi | `60` |
| `JWT_REFRESH_TTL_DAYS` | Refresh token süresi | `30` |
| `INGEST_API_KEY` | Ingestion servis API key | random hex |
| `ENVIRONMENT` | `development` veya `production` | `production` |

### Admin Config (DB'den dinamik)

| Key | Default | Açıklama |
|-----|---------|----------|
| `user_daily_limit` | `5` | Kişi başı günlük soru limiti |
| `total_daily_limit` | `5000` | Günlük toplam soru limiti |
| `rag_top_k` | `10` | Similarity search'te kaç mesaj alınsın |
| `ingestion_lookback_days` | `30` | İlk ingest lookback süresi |

---

## WhatsApp Oturumu Yönetimi

whatsapp-web.js oturumu Docker volume'da persist edilir (`./ingestion-session`). Oturum bir kez başlatıldıktan sonra tekrar QR taramaya gerek yoktur.

**Oturum geçersiz olursa** (WhatsApp hesap logout, uzun süre inaktiflik):
```bash
# Ingestion servisini durdur
docker compose stop ingestion

# Session'ı sil
rm -rf ./ingestion-session

# Yeniden başlat ve QR tara
docker compose up ingestion
docker compose logs -f ingestion
```

---

## Kategoriler

Claude Haiku mesajları aşağıdaki kategorilere atar:

- `araba` — Araç alım/satım, TÜV, sigorta, tamir
- `saglik` — Doktor, hastane, ilaç, sigorta
- `resmi-daire` — Belediye, Ausländerbehörde, Finanzamt, belge işlemleri
- `cocuk` — Okul, kreş, çocuk etkinlikleri
- `ikinci-el` — İkinci el satış/alım
- `konut` — Kira, ev arama, taşınma
- `yemek-restoran` — Restoran, market, Türk ürünleri
- `is-kariyer` — İş ilanları, kariyer, CV
- `egitim` — Dil kursları, üniversite, sertifika
- `spor-eglence` — Spor, etkinlik, gezi
- `genel` — Diğer

---

## İleride Eklenebilecekler

- WhatsApp Bot entegrasyonu (whatsapp-web.js ile yanıt verme, ayrı SIM)
- Telegram bot alternatifi
- Mesaj arama full-text (Türkçe stemming)
- Haftalık özet email (SES)
- Multi-AZ deployment (ASG max=3)
- Kullanıcı bazlı konuşma geçmişi (bağlam sürekliliği)
