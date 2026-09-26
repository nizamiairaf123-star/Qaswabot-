# QASWA VPS Deployment Guide

## 1. Package layout

Extract the package so the application lives at `/opt/qaswa-bot/bot_inspect`.
Do not place secrets in the ZIP.

## 2. Configure secrets

```bash
cd /opt/qaswa-bot/bot_inspect
cp .env.example .env
chmod 600 .env
nano .env
```

Required credentials include Telegram, Dhan and the encryption key. Do not commit or share `.env`.

## 3. Validate package

```bash
cd /opt/qaswa-bot/bot_inspect
python3 -m py_compile ./*.py
bash -n start_bot.sh
bash -n deploy.sh
```

## 4. Install and first start

```bash
./deploy.sh
```

This creates `.venv`, checks the required Python 3.12+, and installs
`requirements.txt`. Then start the bot:

```bash
./start_bot.sh
```

`start_bot.sh` only runs the bot using the already-prepared `.venv` — it
will exit with a clear error telling you to run `./deploy.sh` first if
that hasn't been done yet.

## 5. systemd (recommended)

The supplied unit is a template because the Linux service user is environment-specific. Replace `%i` with the dedicated VPS user if desired, or install a concrete unit under `/etc/systemd/system/qaswa-bot@.service` with the correct `User=`.

```bash
sudo cp qaswa-bot@.service /etc/systemd/system/qaswa-bot@.service
sudo systemctl daemon-reload
sudo systemctl enable --now qaswa-bot@YOUR_USER.service
sudo systemctl status qaswa-bot@YOUR_USER.service
```

## 6. Mandatory trading sequence

Do not jump directly to live trading:

1. `/settoken`
2. `/boardrefresh`
3. `/optimize`
4. `/simulate`
5. deployment approval
6. paper trading
7. staged live approval
8. live only after reconciliation and risk gates are green

## 7. Safety gates

The board universe is fail-closed. Missing, stale, corrupt or failed board verification blocks new BUY entries. The runtime execution universe is strict NSE cash-equity EQ only. Full-universe signal scanning is separate from per-stock deployed-strategy validity; the latter is checked again at the final capital-entry gate.
