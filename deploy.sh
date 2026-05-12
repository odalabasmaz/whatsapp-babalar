#!/usr/bin/env bash
# =============================================================================
# Babalar — AWS Deploy Script
# Kullanım: ./deploy.sh [--skip-secrets] [--infra-only] [--frontend-only]
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CONFIG_FILE="$SCRIPT_DIR/deploy.config"
INFRA_DIR="$SCRIPT_DIR/infrastructure"
FRONTEND_DIR="$SCRIPT_DIR/babalar-frontend"

SKIP_SECRETS=false
INFRA_ONLY=false
FRONTEND_ONLY=false

for arg in "$@"; do
  case $arg in
    --skip-secrets)  SKIP_SECRETS=true ;;
    --infra-only)    INFRA_ONLY=true ;;
    --frontend-only) FRONTEND_ONLY=true ;;
  esac
done

# ── Renk çıktısı ──────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
info()    { echo -e "${CYAN}[•]${NC} $*"; }
success() { echo -e "${GREEN}[✓]${NC} $*"; }
warn()    { echo -e "${YELLOW}[!]${NC} $*"; }
error()   { echo -e "${RED}[✗]${NC} $*"; exit 1; }

# ── Config yükle ──────────────────────────────────────────────────────────────
[[ -f "$CONFIG_FILE" ]] || error "deploy.config bulunamadı. Önce: cp deploy.config.example deploy.config"
# shellcheck source=/dev/null
source "$CONFIG_FILE"

# ── Config doğrula ────────────────────────────────────────────────────────────
validate_config() {
  local missing=()
  for var in AWS_PROFILE AWS_REGION AWS_ACCOUNT_ID REPO_URL EC2_KEY_PAIR \
             DOMAIN ACM_CERT_ARN OPENAI_API_KEY JWT_SECRET INGEST_API_KEY DB_PASSWORD; do
    local val="${!var:-}"
    if [[ -z "$val" || "$val" == *"CHANGE_ME"* ]]; then
      missing+=("$var")
    fi
  done
  if [[ ${#missing[@]} -gt 0 ]]; then
    error "deploy.config içinde doldurulmamış değerler var:\n  ${missing[*]}"
  fi
}

# ── Araç kontrolü ─────────────────────────────────────────────────────────────
check_prerequisites() {
  info "Bağımlılıklar kontrol ediliyor..."
  local missing=()
  command -v aws    &>/dev/null || missing+=("aws-cli")
  command -v cdk    &>/dev/null || missing+=("aws-cdk (npm install -g aws-cdk)")
  command -v node   &>/dev/null || missing+=("node")
  command -v python3 &>/dev/null || missing+=("python3")
  command -v npm    &>/dev/null || missing+=("npm")
  if [[ ${#missing[@]} -gt 0 ]]; then
    error "Eksik araçlar: ${missing[*]}"
  fi
  success "Tüm araçlar mevcut."
}

# ── AWS Secrets Manager ───────────────────────────────────────────────────────
upsert_secret() {
  local name="$1" value="$2"
  if aws secretsmanager describe-secret --secret-id "$name" \
       --region "$AWS_REGION" --profile "$AWS_PROFILE" &>/dev/null; then
    aws secretsmanager put-secret-value \
      --secret-id "$name" --secret-string "$value" \
      --region "$AWS_REGION" --profile "$AWS_PROFILE" --output none
    warn "  Güncellendi: $name"
  else
    aws secretsmanager create-secret \
      --name "$name" --secret-string "$value" \
      --region "$AWS_REGION" --profile "$AWS_PROFILE" --output none
    success "  Oluşturuldu: $name"
  fi
}

create_secrets() {
  info "Secrets Manager'a yükleniyor..."
  # db-password JSON formatında (RDS Credentials şartı)
  upsert_secret "babalar/db-password"    "{\"password\":\"$DB_PASSWORD\"}"
  upsert_secret "babalar/openai-api-key" "$OPENAI_API_KEY"
  upsert_secret "babalar/jwt-secret"     "$JWT_SECRET"
  upsert_secret "babalar/ingest-api-key" "$INGEST_API_KEY"
  success "Secrets hazır."
}

# ── CDK ───────────────────────────────────────────────────────────────────────
CDK_CONTEXT="-c region=$AWS_REGION \
  -c account=$AWS_ACCOUNT_ID \
  -c repo_url=$REPO_URL \
  -c key_pair=$EC2_KEY_PAIR \
  -c domain=$DOMAIN \
  -c cert_arn=$ACM_CERT_ARN"

cdk_run() {
  AWS_PROFILE="$AWS_PROFILE" cdk "$@" $CDK_CONTEXT \
    --app "python3 app.py" \
    --require-approval never \
    --profile "$AWS_PROFILE"
}

bootstrap_cdk() {
  info "CDK bootstrap kontrol ediliyor..."
  if ! AWS_PROFILE="$AWS_PROFILE" aws cloudformation describe-stacks \
      --stack-name "CDKToolkit" --region "$AWS_REGION" \
      --profile "$AWS_PROFILE" &>/dev/null; then
    info "CDK bootstrap çalıştırılıyor..."
    AWS_PROFILE="$AWS_PROFILE" cdk bootstrap \
      "aws://$AWS_ACCOUNT_ID/$AWS_REGION" \
      --profile "$AWS_PROFILE"
    success "CDK bootstrap tamamlandı."
  else
    success "CDK bootstrap zaten yapılmış."
  fi
}

deploy_infra() {
  info "Altyapı stack'leri deploy ediliyor (Network → Database → Compute)..."
  cd "$INFRA_DIR"
  cdk_run deploy BabalarNetwork BabalarDatabase BabalarCompute
  success "Altyapı deploy tamamlandı."
}

get_alb_dns() {
  cd "$INFRA_DIR"
  AWS_PROFILE="$AWS_PROFILE" aws cloudformation describe-stacks \
    --stack-name BabalarNetwork \
    --region "$AWS_REGION" \
    --profile "$AWS_PROFILE" \
    --query "Stacks[0].Outputs[?OutputKey=='AlbDnsName'].OutputValue" \
    --output text
}

build_frontend() {
  local api_url="$1"
  info "Frontend build ediliyor (API: $api_url)..."
  cd "$FRONTEND_DIR"
  npm ci --silent
  VITE_API_URL="$api_url" npm run build
  success "Frontend build tamamlandı."
}

deploy_frontend() {
  info "Frontend stack deploy ediliyor (S3 + CloudFront)..."
  cd "$INFRA_DIR"
  cdk_run deploy BabalarFrontend
  success "Frontend deploy tamamlandı."
}

get_cloudfront_url() {
  cd "$INFRA_DIR"
  AWS_PROFILE="$AWS_PROFILE" aws cloudformation describe-stacks \
    --stack-name BabalarFrontend \
    --region "$AWS_REGION" \
    --profile "$AWS_PROFILE" \
    --query "Stacks[0].Outputs[?OutputKey=='CloudFrontURL'].OutputValue" \
    --output text
}

# ── Ana akış ──────────────────────────────────────────────────────────────────
echo ""
echo "  ======================================"
echo "   Babalar AWS Deploy"
echo "  ======================================"
echo "  Region  : $AWS_REGION"
echo "  Account : $AWS_ACCOUNT_ID"
echo "  Domain  : $DOMAIN"
echo "  Profile : $AWS_PROFILE"
echo "  ======================================"
echo ""

validate_config
check_prerequisites

if [[ "$FRONTEND_ONLY" == false ]]; then
  [[ "$SKIP_SECRETS" == false ]] && create_secrets
  bootstrap_cdk
  deploy_infra
fi

ALB_DNS=$(get_alb_dns)
[[ -z "$ALB_DNS" ]] && error "ALB DNS alınamadı. Infra stack'leri deploy edildi mi?"
info "ALB DNS: $ALB_DNS"

# Frontend API URL: custom domain varsa onu kullan, yoksa ALB
API_URL="https://$DOMAIN"
build_frontend "$API_URL"

[[ "$INFRA_ONLY" == false ]] && deploy_frontend

CLOUDFRONT_URL=$(get_cloudfront_url)

echo ""
echo "  ======================================"
echo -e "   ${GREEN}Deploy Tamamlandı!${NC}"
echo "  ======================================"
echo "  CloudFront : $CLOUDFRONT_URL"
echo "  ALB DNS    : $ALB_DNS"
echo "  Domain     : https://$DOMAIN"
echo "  ======================================"
echo ""
echo "  Sonraki adımlar:"
echo "  1. DNS: $DOMAIN → $ALB_DNS (A/CNAME kaydı)"
echo "  2. EC2 setup logu: ssh ec2-user@<ip> 'tail -f /var/log/babalar-setup.log'"
echo "  3. Admin kur: ssh ec2-user@<ip> 'cd /app && docker compose -f docker-compose.prod.yml exec backend python -m app.cli setup'"
echo "  4. WhatsApp: Admin paneli → Gruplar sekmesi → QR kodu tara"
echo ""
