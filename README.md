# Babalar

WhatsApp grup konuşmalarını indeksleyen, vektör veritabanına kaydeden ve kullanıcıların Türkçe soru sorabileceği RAG tabanlı bir chatbot.

## Mimari

```
[React Frontend] ──→ [FastAPI Backend :8000] ──→ [PostgreSQL + pgvector]
                                                          ↑
                      [Node.js Ingestion] ────────────────┘
```

- **Backend** — FastAPI, SQLAlchemy async, pgvector (1536-dim HNSW)
- **Frontend** — React 18, TypeScript, Vite, Tailwind CSS, Zustand
- **Ingestion** — Node.js, whatsapp-web.js, cron tabanlı
- **LLM** — GPT-4o-mini (soru yanıtlama, kategorizasyon) + text-embedding-3-small
- **Infra** — AWS (EC2, RDS PostgreSQL 16, CloudFront + S3), CDK (Python)

---

## Yerel Kurulum

### Gereksinimler

- Docker & Docker Compose
- Node.js 20+ (opsiyonel, Docker dışı frontend geliştirme için)

### 1. Config

```bash
cp .env.example .env
# .env dosyasını düzenle — en azından OPENAI_API_KEY, JWT_SECRET, INGEST_API_KEY doldurulmalı
```

### 2. Başlat

```bash
./run.sh          # docker compose up -d
```

İlk başlatmada migration ve admin kurulumu:

```bash
docker compose exec backend alembic upgrade head
docker compose exec backend python -m app.cli setup
```

### 3. Yerel URL'ler

| Servis | URL |
|--------|-----|
| Frontend | http://localhost:5173 |
| Backend API | http://localhost:8000 |
| Swagger Docs | http://localhost:8000/docs |

### run.sh Komutları

```bash
./run.sh              # Başlat (varsayılan)
./run.sh down         # Durdur
./run.sh restart      # Yeniden başlat
./run.sh logs         # Tüm loglar
./run.sh logs backend # Belirli servis logu
./run.sh status       # Konteyner durumu
```

---

## WhatsApp Bağlantısı

İlk bağlantıda WhatsApp Web QR kodu taranması gerekir. İki yol:

**Yerel:** `docker compose logs ingestion` çıktısında QR terminale basılır.

**AWS:** Admin paneli → Gruplar sekmesi → QR kodu ekranda görünür, telefonla tara.

Bağlantı koptuğunda (LOGOUT) ingestion konteyneri otomatik yeniden başlar ve yeni QR üretir.

---

## AWS Deploy

### Ön Koşullar

```bash
npm install -g aws-cdk
aws configure --profile <profil-adı>
```

ACM sertifikası (bir kez, manuel):
1. AWS Console → Certificate Manager → **us-east-1** → Request certificate
2. Domain: `your-domain.com`
3. DNS validation → CNAME'leri domain sağlayıcına ekle → "Issued" bekle
4. Sertifika ARN'ini `deploy.config`'e yaz

### 1. Config

```bash
cp deploy.config.example deploy.config
# deploy.config'i aç, tüm değerleri doldur
```

| Değer | Açıklama |
|-------|----------|
| `AWS_PROFILE` | `aws configure` ile ayarlanmış profil adı |
| `AWS_REGION` | Varsayılan: `eu-central-1` |
| `AWS_ACCOUNT_ID` | 12 haneli AWS hesap numarası |
| `REPO_URL` | EC2'nin clone'layacağı repo URL'i |
| `EC2_KEY_PAIR` | EC2 → Key Pairs'teki key pair adı |
| `DOMAIN` | Uygulamanın domain'i (`babalar.example.com`) |
| `ACM_CERT_ARN` | us-east-1'deki ACM sertifika ARN'i |
| `OPENAI_API_KEY` | OpenAI API anahtarı |
| `JWT_SECRET` | En az 32 karakter (`openssl rand -hex 32`) |
| `INGEST_API_KEY` | Backend-ingestion arası dahili key (`openssl rand -hex 32`) |
| `DB_PASSWORD` | PostgreSQL şifresi |

### 2. Deploy

```bash
./deploy.sh
```

Script sırasıyla şunları yapar:

1. `deploy.config` değerlerini doğrular
2. Secrets'ları AWS Secrets Manager'a yükler
3. CDK bootstrap (ilk deploy'da gerekli, sonra atlar)
4. **Network** → **Database** → **Compute** stack'lerini deploy eder
5. EC2 açılışında otomatik olarak repo'yu clone'lar, `.env` oluşturur, migration çalıştırır
6. Frontend'i build eder (`VITE_API_URL=https://domain`)
7. **Frontend** stack'ini deploy eder (S3 + CloudFront)
8. URL'leri ve sonraki adımları yazdırır

**Script seçenekleri:**

```bash
./deploy.sh --skip-secrets   # Secrets zaten varsa yeniden yazmaz
./deploy.sh --infra-only     # Sadece EC2/RDS, frontend'e dokunmaz
./deploy.sh --frontend-only  # Sadece frontend yeniden deploy
```

### 3. Deploy Sonrası

```bash
# DNS kaydı ekle (domain sağlayıcında)
# your-domain.com → ALB DNS adı (script sonunda gösterilir)

# EC2 setup logunu izle
ssh ec2-user@<ec2-ip> 'tail -f /var/log/babalar-setup.log'

# Admin kullanıcısı oluştur
ssh ec2-user@<ec2-ip> 'cd /app && docker compose -f docker-compose.prod.yml exec backend python -m app.cli setup'

# WhatsApp QR tara
# Admin paneli → Gruplar sekmesi
```

### AWS Altyapısı

| Kaynak | Tip | Açıklama |
|--------|-----|----------|
| EC2 | t4g.small (Graviton2) | Backend + ingestion, ~$15/ay |
| RDS | t4g.micro PostgreSQL 16 | pgvector, private subnet, ~$13/ay |
| ALB | Application Load Balancer | HTTPS termination |
| CloudFront + S3 | — | Frontend, sadece Almanya (geo-restriction) |
| Secrets Manager | — | API anahtarları, DB şifresi |

---

## Veritabanı Migration

```bash
# Yerel
docker compose exec backend alembic upgrade head

# Yeni migration oluştur
docker compose exec backend alembic revision --autogenerate -m "açıklama"
```

---

## Proje Yapısı

```
babalar/
├── babalar-backend/        # FastAPI uygulaması
│   ├── app/
│   │   ├── api/            # Route handler'lar (auth, chat, admin, ingest)
│   │   ├── services/       # İş mantığı (rag, embedding, categorizer, rate_limiter)
│   │   └── models/         # SQLAlchemy ORM modelleri
│   └── alembic/            # DB migration'ları
├── babalar-frontend/       # React uygulaması
│   └── src/
│       ├── pages/          # ChatPage, AdminPage, LoginPage, RegisterPage
│       ├── store/          # Zustand store (auth, theme)
│       └── api/            # Axios client
├── babalar-ingestion/      # WhatsApp veri toplama servisi
│   └── src/
│       ├── index.js        # Giriş noktası, cron + trigger polling
│       ├── scheduler.js    # Gruplara göre veri çekme mantığı
│       ├── whatsapp.js     # whatsapp-web.js bağlantısı, QR yönetimi
│       └── api-client.js   # Backend'e mesaj/durum gönderme
├── infrastructure/         # AWS CDK (Python)
│   └── stacks/
│       ├── network_stack.py   # VPC, ALB, Security Groups
│       ├── database_stack.py  # RDS PostgreSQL
│       ├── compute_stack.py   # EC2, ASG, user data
│       └── frontend_stack.py  # S3, CloudFront
├── deploy.config.example   # Deploy config şablonu
├── deploy.sh               # AWS deploy script
├── docker-compose.yml      # Yerel geliştirme
├── docker-compose.prod.yml # Production (postgres ve frontend yok)
└── run.sh                  # Yerel başlatma yardımcısı
```
