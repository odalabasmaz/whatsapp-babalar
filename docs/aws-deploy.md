# Babalar — AWS Deploy Guide

Follow these steps in order to deploy Babalar to AWS.
Don't skip any step and you won't run into problems.

---

## What we're doing

```
Your machine
  → connects to AWS (IAM user)
  → provisions infrastructure (VPC, EC2, RDS, CloudFront)
  → uploads secrets to a secure vault (Secrets Manager)
  → builds the frontend and pushes it to the CDN
  → EC2 bootstraps itself: clones the repo, runs migrations, starts services
```

Total time: ~30 minutes (includes CDK deploy wait times).

---

## Prerequisites

The following tools must be installed on your machine:

```bash
# Verify
aws --version    # aws-cli v2
cdk --version    # 2.x
node --version   # 20+
python --version # 3.9+
npm --version
```

Install missing tools:

```bash
# AWS CLI (Mac)
brew install awscli

# CDK
npm install -g aws-cdk

# Node.js (Mac)
brew install node

# Python (Mac) — if `python` is missing or too old
brew install python
```

---

## Step 1 — AWS account and IAM setup

> **Why?** We need an identity to connect to AWS from the command line.
> CDK deployments involve two separate IAM identities:
> - **`babalar-deployer`** — your machine's identity. Only allowed to trigger CDK deployments (assume CDK roles). If this key leaks, an attacker can't directly touch EC2, RDS, or S3.
> - **CDK execution role** — auto-created by CDK bootstrap. This is what CloudFormation actually uses to create resources. It's only assumable by CloudFormation, not humans.

### 1.1 Create the `BabalarDeployerPolicy` custom policy

1. Open [AWS Console → IAM → Policies → Create policy](https://console.aws.amazon.com/iam/home#/policies/create)
2. Click **JSON** and paste:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "sts:AssumeRole",
      "Resource": "arn:aws:iam::ACCOUNT_ID:role/cdk-*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "cloudformation:DescribeStacks",
        "cloudformation:ListStacks",
        "ssm:GetParameter",
        "ssm:StartSession",
        "ssm:SendCommand",
        "ssm:GetCommandInvocation",
        "ssm:TerminateSession",
        "ec2:DescribeInstances",
        "secretsmanager:CreateSecret",
        "secretsmanager:PutSecretValue",
        "secretsmanager:DescribeSecret"
      ],
      "Resource": "*"
    }
  ]
}
```

3. Replace `ACCOUNT_ID` with your 12-digit AWS account number (visible in the top-right of the console)
4. Click **Next** → Policy name: `BabalarDeployerPolicy` → **Create policy**

### 1.2 Create the `babalar-deployer` IAM user

1. Open [AWS Console → IAM → Users → Create user](https://console.aws.amazon.com/iam/home#/users/create)
2. User name: `babalar-deployer`
3. Click **Next**
4. Permission options: **Attach policies directly**
5. Search for and select `BabalarDeployerPolicy`
6. Click **Create user**

### 1.3 Create an access key

1. Click on the user you just created → **Security credentials** tab
2. Click **Create access key**
3. Use case: **Command Line Interface (CLI)**
4. Click **Create access key**
5. Copy the **Access key ID** and **Secret access key** somewhere safe — you won't be able to see them again after closing this page


### 1.4 Configure the AWS CLI

```bash
aws configure --profile babalar
```

Fill in the prompts:

```
AWS Access Key ID:     <Access key ID from step 1.3>
AWS Secret Access Key: <Secret access key from step 1.3>
Default region name:   eu-central-1
Default output format: json
```

Verify it works:

```bash
aws sts get-caller-identity --profile babalar
# Output should show "Account", "UserId", "Arn"
```

### 1.5 Bootstrap CDK (one-time, needs temporary admin)

> **Why?** CDK bootstrap creates the S3 bucket, ECR repo, and IAM roles it needs to operate.
> This only runs once per AWS account/region. After this, `babalar-deployer` has all it needs.
> The bootstrap execution role is assumable only by CloudFormation — not by the deployer key.

Temporarily attach `AdministratorAccess` to `babalar-deployer`:

1. AWS Console → IAM → Users → `babalar-deployer` → **Add permissions**
2. **Attach policies directly** → select `AdministratorAccess` → **Add permissions**

Run bootstrap:

```bash
cdk bootstrap aws://ACCOUNT_ID/eu-central-1 --profile babalar
```

Then immediately remove the temporary admin permission:

1. AWS Console → IAM → Users → `babalar-deployer` → **Permissions** tab
2. Click the `X` next to `AdministratorAccess` → **Remove**

From this point on, `babalar-deployer` only has `BabalarDeployerPolicy` — scoped and safe.

---

## Step 2 — Prepare secrets

> **Why?** Passwords and API keys must not live in the code.
> We store them in AWS Secrets Manager; EC2 reads them on startup.

Generate the values you'll need:

```bash
# OpenAI API key — get from platform.openai.com → API Keys
OPENAI_API_KEY=sk-...

# JWT secret — at least 32 random characters
openssl rand -hex 32   # use the output as JWT_SECRET

# Ingestion API key — internal key shared between backend and ingestion service
openssl rand -hex 32   # use the output as INGEST_API_KEY

# Database password
openssl rand -hex 16   # use the output as DB_PASSWORD

```

Keep these handy — you'll put them in `deploy.config` in the next step.

---

## Step 3 — SSL certificate (for CloudFront)

> **Why?** CloudFront requires an ACM certificate for HTTPS.
> Because CloudFront is a global service, the certificate must be in **us-east-1**.
> This is a one-time manual step.

1. Open [AWS Console → Certificate Manager](https://console.aws.amazon.com/acm/home?region=us-east-1) — **set region to us-east-1**
2. Click **Request a certificate** → **Request a public certificate**
3. Domain: `babalar.example.com` (your own domain)
4. Validation method: **DNS validation**
5. Click **Request**
6. Click on the certificate you just created → note the **CNAME name** and **CNAME value**
7. Add these CNAMEs to your domain provider (Namecheap, GoDaddy, etc.)
8. Wait a few minutes until the status shows **Issued**
9. Copy the certificate ARN (looks like: `arn:aws:acm:us-east-1:123456789:certificate/abc-def`)

---

## Step 4 — Fill in the deploy config

```bash
cp deploy.config.example deploy.config
```

Open `deploy.config` and fill in all values:

```bash
AWS_PROFILE=babalar           # Profile name from step 1.3
AWS_REGION=eu-central-1
AWS_ACCOUNT_ID=123456789012   # 12-digit number shown in the top-right of AWS Console

REPO_URL=https://github.com/YOUR_ORG/babalar.git   # This repo's URL

DOMAIN=babalar.example.com      # The domain your app will run on
ACM_CERT_ARN=arn:aws:acm:us-east-1:...:certificate/...  # ARN from step 3

OPENAI_API_KEY=sk-...
JWT_SECRET=...                  # output of: openssl rand -hex 32
INGEST_API_KEY=...              # output of: openssl rand -hex 32
DB_PASSWORD=...                 # output of: openssl rand -hex 16
```

> `deploy.config` is in `.gitignore` — it won't be committed to the repo.

---

## Step 5 — Deploy

```bash
./deploy.sh
```

The script runs these steps in order:

| Step | What it does | Duration |
|------|-------------|----------|
| Secrets | Uploads keys/passwords to Secrets Manager | ~30 sec |
| BabalarNetwork | VPC, subnets, security groups, ALB | ~3 min |
| BabalarDatabase | RDS PostgreSQL 16 (private subnet) | ~10 min |
| BabalarCompute | EC2, Auto Scaling Group | ~3 min |
| Frontend build | Builds the React app | ~1 min |
| BabalarFrontend | S3 bucket + CloudFront distribution | ~5 min |

> CDK bootstrap is **not** run by this script — you already did it manually in Step 1.5.

When deploy finishes you'll see:

```
  ======================================
   Deploy Complete!
  ======================================
  CloudFront : https://xxx.cloudfront.net
  ALB DNS    : babalar-xxx.eu-central-1.elb.amazonaws.com
  Domain     : https://babalar.example.com
  ======================================
```

**Partial deploy options:**

```bash
./deploy.sh --skip-secrets    # Don't re-upload secrets (already exist)
./deploy.sh --infra-only      # EC2/RDS only, skip frontend
./deploy.sh --frontend-only   # Redeploy frontend only
```

---

## Step 6 — Add a DNS record

> **Why?** Your domain needs to point to CloudFront. All traffic (frontend + API) goes through CloudFront — it's the single entry point. Do **not** point DNS at the ALB directly.

### CNAME vs A record — when to use which

| Situation | Record type | Reason |
|-----------|-------------|--------|
| Subdomain (e.g. `babalar.ocloudy.com`) | **CNAME** | Points hostname → hostname. Correct choice here. |
| Root/apex domain (e.g. `ocloudy.com`) | **ALIAS or ANAME** (not plain CNAME) | The DNS spec forbids CNAME at the apex. Route 53 calls it "Alias"; many other providers call it "ANAME". Functionally identical to CNAME — use it when available. |

CloudFront only exposes a hostname (e.g. `dxxxx.cloudfront.net`), never a static IP, so a plain A record is not possible.

### Add the record

The CloudFront domain is shown at the end of `./deploy.sh`. Add the following at your domain provider:

| Type | Name | Value |
|------|------|-------|
| CNAME | `babalar` | `dxxxx.cloudfront.net` (from deploy output) |

Example (Namecheap Advanced DNS):
- Type: `CNAME Record`
- Host: `babalar`
- Value: `d3uizggjo17rr4.cloudfront.net` ← your actual CloudFront domain

DNS propagates in 1–5 minutes. Verify with:

```bash
dig babalar.example.com CNAME +short
# Should print:  dxxxx.cloudfront.net.
```

---

## Step 7 — Watch the EC2 setup

When EC2 starts, it clones the repo, runs migrations, and brings up all services.
You can follow this over SSM — no SSH required, port 22 is closed.

### Get the instance ID

```bash
aws ec2 describe-instances \
  --filters "Name=tag:aws:cloudformation:stack-name,Values=BabalarCompute" \
  --query "Reservations[].Instances[].InstanceId" \
  --output text \
  --region eu-central-1 --profile babalar
# Example output: i-0abc1234def56789
```

### Connect to the instance

```bash
aws ssm start-session \
  --target i-0abc1234def56789 \
  --region eu-central-1 --profile babalar
```

Once connected, tail the setup log:

```bash
tail -f /var/log/babalar-setup.log
```

When you see `Setup complete.` at the end, move on to the next step.

---

## Step 8 — Create the admin user

In the SSM session (while still connected):

```bash
docker compose -f /app/docker-compose.prod.yml exec backend python -m app.cli setup
```

This command:
- Prompts for an admin username and password
- Generates the first invite code

Save the output — you'll share the invite code with your users.

---

## Step 9 — Connect WhatsApp

1. Open `https://babalar.example.com` in your browser
2. Log in with the admin credentials you just created
3. Go to **Admin panel → Groups** tab
4. Scan the QR code with your phone:
   - WhatsApp → Settings → Linked Devices → Link a Device

Once connected, the ingestion service runs automatically every night at 02:00 UTC.

---

## IAM summary

| Identity | Permission | Purpose |
|----------|-----------|---------|
| `babalar-deployer` (IAM user) | `BabalarDeployerPolicy` — assume CDK roles + Secrets Manager write | Triggers deployments from your machine; cannot directly touch any resource |
| CDK execution role (created by bootstrap) | Broad (creates all infra) — assumable by CloudFormation only | What actually creates VPC, EC2, RDS, S3, etc. |
| `BabalarCompute/EC2Role` (created by CDK) | CloudWatchLogsFullAccess + SSM + Secrets Manager read | EC2 reads secrets, accepts SSM connections, writes logs |

---

## Troubleshooting

**Deploy failed mid-way:**

```bash
# See which resource failed and why
aws cloudformation describe-stack-events \
  --stack-name BabalarCompute \
  --region eu-central-1 --profile babalar \
  --query "StackEvents[?ResourceStatus=='CREATE_FAILED'].[LogicalResourceId,ResourceStatusReason]" \
  --output table
```

**EC2 setup failed:**

Connect via SSM and read the log:

```bash
cat /var/log/babalar-setup.log
```

**Backend won't start:**

```bash
# Inside the SSM session
docker compose -f /app/docker-compose.prod.yml logs backend
```

**I want to tear everything down and redeploy from scratch:**

```bash
# Note: the database is NOT deleted (deletion_protection=True)
cd infrastructure
cdk destroy --all --profile babalar
# Then redeploy: ./deploy.sh
```
