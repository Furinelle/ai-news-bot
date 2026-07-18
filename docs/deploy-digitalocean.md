# Deploy on DigitalOcean Ubuntu

This guide deploys AI News Bot on a DigitalOcean Droplet with Ubuntu 24.04 and root password login.

The screenshot-provided public IPv4 is:

```text
206.189.150.222
```

## 1. SSH into the VPS

From Windows PowerShell:

```powershell
ssh root@206.189.150.222
```

Type the root password when prompted. For security, the password will not be shown while typing.

If SSH asks whether to trust the host fingerprint, type `yes`.

## 2. Install system packages

```bash
apt update
apt install -y git python3 python3-venv python3-pip ca-certificates
timedatectl set-timezone Asia/Shanghai
```

## 3. Clone the public repository

```bash
mkdir -p /opt
cd /opt
git clone https://github.com/Furinelle/ai-news-bot.git
cd /opt/ai-news-bot
```

## 4. Create the Python environment

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## 5. Create local config files

```bash
cp config.example.json config.json
cp sources.example.json sources.json
mkdir -p reports data
```

Edit `config.json` if you want to use a non-OpenAI provider:

```bash
nano config.json
```

For any OpenAI-compatible provider, change only:

```json
{
  "llm": {
    "base_url": "https://api.example.com/v1",
    "model": "your-model-name",
    "timeout_seconds": 180
  }
}
```

For DeepSeek, a practical starting point is:

```json
{
  "llm": {
    "base_url": "https://api.deepseek.com",
    "model": "deepseek-v4-flash",
    "timeout_seconds": 240,
    "thinking_enabled": true,
    "reasoning_effort": "high"
  }
}
```

If a longer report times out, increase `timeout_seconds` to `300`, or reduce `limits.max_report_items` to `12`.

When `r2.public_base_url` is empty, the notification uses a private R2 presigned URL for the HTML report. The default link lifetime is 7 days:

```json
{
  "r2": {
    "public_base_url": "",
    "presigned_url_expires_seconds": 604800
  }
}
```

## 6. Store secrets outside the repository

```bash
nano /etc/ai-news-bot.env
```

Example:

```env
LLM_API_KEY=replace-with-your-llm-api-key
SCRIPTING_PUSH_API_KEY=replace-with-your-scripting-remote-push-key
CLOUDFLARE_ACCOUNT_ID=replace-with-your-cloudflare-account-id
R2_ACCESS_KEY_ID=replace-with-your-r2-access-key-id
R2_SECRET_ACCESS_KEY=replace-with-your-r2-secret-access-key
```

Lock down the secret file:

```bash
chmod 600 /etc/ai-news-bot.env
```

## 7. Test without LLM or push

```bash
set -a
. /etc/ai-news-bot.env
set +a

cd /opt/ai-news-bot
. .venv/bin/activate
python -m ai_news_bot.main --config config.json --sources sources.json --dry-run --no-llm
```

This fallback mode keeps original source titles, so English sources may remain English. For a Chinese report, run the next LLM test without `--no-llm`.

## 8. Test with LLM but without push

```bash
python -m ai_news_bot.main --config config.json --sources sources.json --dry-run
```

## 9. Test Scripting Remote Push and R2 upload

```bash
python -m ai_news_bot.main --config config.json --sources sources.json --send
```

If your iPhone receives the notification, opens the HTML report, and the R2 objects appear in the bucket, continue to systemd.

## 10. Install systemd service and timer

```bash
cp /opt/ai-news-bot/deploy/systemd/ai-news-bot.service /etc/systemd/system/ai-news-bot.service
cp /opt/ai-news-bot/deploy/systemd/ai-news-bot.timer /etc/systemd/system/ai-news-bot.timer

systemctl daemon-reload
systemctl enable --now ai-news-bot.timer
```

Check the timer:

```bash
systemctl list-timers ai-news-bot.timer
```

Run once manually through systemd:

```bash
systemctl start ai-news-bot.service
journalctl -u ai-news-bot.service -n 100 --no-pager
```

## 11. Update later

```bash
cd /opt/ai-news-bot
git pull
. .venv/bin/activate
python -m pip install -r requirements.txt
systemctl restart ai-news-bot.timer
```

## Notes

- `config.json`, `sources.json`, `data/`, and `reports/` stay local on the VPS.
- Do not commit real API keys, Scripting Remote Push keys, or R2 credentials.
- R2 uses Cloudflare's S3-compatible endpoint: `https://<ACCOUNT_ID>.r2.cloudflarestorage.com`.
