# Ironhold Tactical — Demo Storefront

A Django e-commerce demo (tactical/military theme) used as a showcase site for
selling websites to businesses. Bilingual (English / Spanish), with a product
catalog, cart, customer accounts, an order-tracking flow, and an admin back
office for fulfilling orders.

- **Framework:** Django 6, Python 3.14
- **Database:** SQLite (fine for a demo; swap to PostgreSQL for real traffic)
- **Static files:** WhiteNoise (served by the app process)
- **Production server:** Gunicorn behind Nginx

---

## 1. Local development

```bash
# from the repo root (the folder containing manage.py)
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

python manage.py migrate           # set up the database
python manage.py seed_demo --reset # load demo catalog + demo customer + sample orders
python manage.py compilemessages   # build the Spanish translations (.po -> .mo)
python manage.py runserver         # http://127.0.0.1:8000
```

Create your own admin account with `python manage.py createsuperuser`.

### Demo logins (created by `seed_demo`)

| Purpose | URL | Login | Password |
|---|---|---|---|
| Shop customer (has sample orders) | `/login/` | `demo@ironhold.co` | `demo12345` |
| Admin back office | `/admin/` | *your superuser* | — |

> ⚠️ The demo passwords are for local testing. Remove or change them before a
> public launch.

---

## 2. Everyday tasks

### Reset / reload the demo data
```bash
python manage.py seed_demo --reset   # wipes products + reloads the full demo
python manage.py seed_demo           # adds anything missing, keeps existing rows
```

### Managing orders (fulfillment)
1. Sign in at `/admin/` and open **Orders**.
2. Each order shows a colour-coded status: 🟡 New · 🔵 Shipped · 🟢 Delivered.
3. (Optional) type a **tracking number** into the row and click **Save**.
4. Tick one or more orders → **Action ▾ → “Mark selected orders as SHIPPED (sent)”** → **Go**.
   (There is also “Mark as DELIVERED”.)

The customer sees the status update on their **Account** (`/account/`) and
**Missions** (`/orders/`) pages, including the tracking number once shipped.

### Translations (i18n)

**Spanish is the source language.** The text inside `{% trans "…" %}` in the
templates is Spanish, so Spanish needs no catalog — it renders as written.
English is produced by translating those Spanish strings in `locale/en/`.

After adding or editing any `{% trans %}` text:
```bash
python manage.py makemessages -l en   # extract new strings into locale/en/.../django.po
# ...open that file and fill in the English for each new msgstr ""...
python manage.py compilemessages      # compile .po -> .mo  (REQUIRED; Django only reads .mo)
```
> If English “stops working”, it is almost always a missing `compilemessages`,
> a server that was not restarted, or a new Spanish string with an empty
> `msgstr`. `./check.sh` catches the last one for you.

### Running the checks
```bash
./check.sh          # everything: config, migrations, translations, tests, prod render
./check.sh --fast   # same minus the production-mode render pass
```
Run it before every commit and after every `git pull`. See §6.

---

## 3. Deploying to an Arch Linux VPS

This is a repeatable checklist. Replace `ironhold.example` with your domain and
`ironhold` with whatever service user you prefer. Run as a sudo-capable user.

### 3.1 Point your domain
- Create an **A record** for `ironhold.example` → your VPS IP (and `www` too).

### 3.2 Install system packages
```bash
sudo pacman -Syu --needed python git nginx
# for HTTPS certificates:
sudo pacman -S --needed certbot certbot-nginx
```

### 3.3 Create a service user and fetch the code
```bash
sudo useradd -m -s /bin/bash ironhold
sudo -iu ironhold
git clone <YOUR_REPO_URL> ~/ecommerce      # ~/ecommerce now contains manage.py
cd ~/ecommerce
```

### 3.4 Python environment
```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3.5 Create the environment file
Generate a secret key:
```bash
python -c "from django.core.management.utils import get_random_secret_key as k; print(k())"
```
Create `~/ecommerce/.env` (owned by the `ironhold` user, `chmod 600`):
```ini
DJANGO_DEBUG=False
DJANGO_SECRET_KEY=paste-the-generated-key-here
DJANGO_ALLOWED_HOSTS=ironhold.example,www.ironhold.example
DJANGO_CSRF_TRUSTED_ORIGINS=https://ironhold.example,https://www.ironhold.example
# Keep this False until HTTPS is working (step 3.9), then set True and restart:
DJANGO_SECURE_SSL_REDIRECT=False

# --- Stripe (see §7). Omit these and the store records orders as unpaid. ---
STRIPE_PUBLISHABLE_KEY=pk_live_xxx
STRIPE_SECRET_KEY=sk_live_xxx
STRIPE_WEBHOOK_SECRET=whsec_xxx
STRIPE_CURRENCY=usd
```

### 3.6 Initialize the app
```bash
set -a; source .env; set +a          # load the env into this shell
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py compilemessages
python manage.py seed_demo           # optional: load the demo catalog
python manage.py createsuperuser     # your admin account
exit                                 # leave the ironhold user
```

### 3.7 Gunicorn systemd service
Create `/etc/systemd/system/ironhold.service`:
```ini
[Unit]
Description=Ironhold Tactical (gunicorn)
After=network.target

[Service]
User=ironhold
Group=ironhold
WorkingDirectory=/home/ironhold/ecommerce
RuntimeDirectory=ironhold
EnvironmentFile=/home/ironhold/ecommerce/.env
ExecStart=/home/ironhold/ecommerce/venv/bin/gunicorn \
    --workers 3 \
    --bind unix:/run/ironhold/gunicorn.sock \
    ecommerce.wsgi:application
Restart=always

[Install]
WantedBy=multi-user.target
```
Enable it:
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now ironhold
sudo systemctl status ironhold        # should be "active (running)"
```

### 3.8 Nginx reverse proxy
Create `/etc/nginx/conf.d/ironhold.conf`:
```nginx
server {
    listen 80;
    server_name ironhold.example www.ironhold.example;
    client_max_body_size 10M;

    # user-uploaded media (product images). Static files are served by WhiteNoise.
    location /media/ {
        alias /home/ironhold/ecommerce/media/;
    }

    location / {
        proxy_pass http://unix:/run/ironhold/gunicorn.sock;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```
Make sure Arch's `/etc/nginx/nginx.conf` includes `conf.d` inside its `http { }`
block (add if missing): `include /etc/nginx/conf.d/*.conf;`
Then:
```bash
sudo nginx -t && sudo systemctl enable --now nginx
# let nginx read the media files in the ironhold home dir:
sudo chmod o+x /home/ironhold
```

### 3.9 HTTPS
```bash
sudo certbot --nginx -d ironhold.example -d www.ironhold.example
```
Certbot adds the TLS config and an http→https redirect. Now turn on Django’s
own HTTPS enforcement:
```bash
# edit /home/ironhold/ecommerce/.env  ->  DJANGO_SECURE_SSL_REDIRECT=True
sudo systemctl restart ironhold
```

### 3.10 Firewall (optional but recommended)
```bash
sudo pacman -S --needed ufw
sudo ufw allow 22/tcp && sudo ufw allow 80/tcp && sudo ufw allow 443/tcp
sudo ufw enable
```

### 3.11 Verify
```bash
sudo systemctl status ironhold nginx
curl -I https://ironhold.example        # expect HTTP/2 200
python manage.py check --deploy         # (as ironhold, env loaded) should be clean
```

---

## 4. Redeploying after code changes
```bash
sudo -iu ironhold
cd ~/ecommerce && source venv/bin/activate && set -a && source .env && set +a
git pull
pip install -r requirements.txt
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py compilemessages
exit
sudo systemctl restart ironhold
```

---

## 5. Going-live checklist
- [ ] `DJANGO_DEBUG=False`
- [ ] Fresh `DJANGO_SECRET_KEY` in `.env` (never commit it)
- [ ] `DJANGO_ALLOWED_HOSTS` + `DJANGO_CSRF_TRUSTED_ORIGINS` set to your domain
- [ ] `DJANGO_SECURE_SSL_REDIRECT=True` after HTTPS works
- [ ] Removed/changed the `demo@ironhold.co` customer and any demo admin
- [ ] `python manage.py check --deploy` is clean
- [ ] (Scale) switch SQLite → PostgreSQL, and consider self-hosting the Google Fonts

---

## 6. Testing — run this after every change

```bash
./check.sh
```

Six gates, failing fast on the first problem:

| # | Gate | Catches |
|---|------|---------|
| 1 | `manage.py check` | broken settings, bad admin config |
| 2 | `makemigrations --check` | a model edited without a migration |
| 3 | `migrate --check` | migrations written but never applied |
| 4 | `compilemessages` | a `.po` that will not compile |
| 5 | `manage.py test store` | the full suite (99 tests) |
| 6 | `collectstatic` + render with `DEBUG=False` | `{% static %}` pointing at a missing file — invisible in dev, a hard 500 in production |

Run one group while working on it:
```bash
python manage.py test store.tests.test_payments   # Stripe
python manage.py test store.tests.test_cart       # cart logic
python manage.py test store.tests.test_smoke      # pages render
python manage.py test store.tests.test_auth       # login / access control
python manage.py test store.tests.test_checkout   # order creation
python manage.py test store.tests.test_i18n       # translations
```

What the suite covers:

- **Smoke** — every page returns the expected status; every named URL reverses.
- **Auth** — signup validation, password hashing, login/logout, protected pages
  redirect, and the open-redirect guard on `?return_url=`.
- **Cart** — add/increment/decrement/remove, colour variants as separate lines,
  and that stale or malformed cart cookies are dropped instead of crashing.
- **Checkout** — one order per cart line, address snapshotting, cart cleared,
  and that a POSTed `price` can never override the catalogue price.
- **Payments** — cent conversion, amounts sent to Stripe match the database,
  webhook signature verification (real HMAC, including forged/tampered/wrong-secret
  cases), and that confirming a payment twice is a no-op.
- **i18n** — the language switcher works both directions and no Spanish string
  is left without an English translation.

> **Before pushing, always:** `./check.sh` → commit → push. On the VPS after
> pulling, run `./check.sh --fast` before restarting the service.

---

## 7. Stripe payments

### 7.1 Get your keys
1. Create an account at <https://dashboard.stripe.com/register> and complete
   the business profile.
2. Keep the **Test mode** toggle ON while developing.
3. **Developers → API keys** → copy the **Publishable key** (`pk_test_…`) and
   reveal + copy the **Secret key** (`sk_test_…`).
4. Put both in `.env` (never in git).

`.env` lives next to `manage.py` and is read at startup by `settings.py`.
Start from the template:

```bash
cp .env.example .env      # then edit in your real keys
```

Real environment variables take priority over the file, so a `export` in the
shell or a systemd `Environment=` line overrides it — production sets secrets
that way and needs no `.env` on disk at all.

> Django does **not** read `.env` on its own; `python-dotenv` (in
> `requirements.txt`) is what makes it work. If you installed dependencies
> before it was added, run `pip install -r requirements.txt` again or the file
> is silently ignored and Stripe stays disabled.

### 7.2 Test locally
```bash
# terminal 1 — keys come from .env; no export needed
python manage.py runserver

# terminal 2 — forward Stripe's webhooks to your machine
stripe login
stripe listen --forward-to localhost:8000/stripe/webhook/
# copy the whsec_… it prints into STRIPE_WEBHOOK_SECRET in .env,
# then restart terminal 1 (settings are only read at startup)
```

Test cards (any future expiry, any CVC, any ZIP):

| Card number | Result |
|---|---|
| `4242 4242 4242 4242` | payment succeeds |
| `4000 0000 0000 9995` | declined — insufficient funds |
| `4000 0025 0000 3155` | requires 3D Secure authentication |
| `4000 0000 0000 0341` | attaches, then fails when charged |

### 7.3 Go live
1. Flip the dashboard to **Live mode** and copy the `pk_live_…` / `sk_live_…` keys.
2. **Developers → Webhooks → Add endpoint**
   - URL: `https://yourdomain.com/stripe/webhook/`
   - Events: `checkout.session.completed`, `checkout.session.expired`,
     `checkout.session.async_payment_succeeded`,
     `checkout.session.async_payment_failed`
3. Copy that endpoint's **Signing secret** into `STRIPE_WEBHOOK_SECRET`.
4. `sudo systemctl restart ironhold`.

### 7.4 How it works
1. Shopper submits the checkout form → the server prices the cart **from the
   database** and creates a Stripe Checkout Session.
2. Orders are saved as `payment_status=pending`, tagged with the session id.
3. Shopper is redirected to Stripe's hosted page. **Card details never touch
   this server**, which keeps PCI scope with Stripe.
4. On success Stripe redirects back to `/checkout/success/` **and** sends a
   `checkout.session.completed` webhook. Either path marks the orders paid;
   whichever arrives second is a no-op.
5. The cart is cleared only once payment is confirmed — cancelling on Stripe
   returns the shopper to a full cart.

> With no `STRIPE_SECRET_KEY` set, checkout still works: orders are recorded as
> **awaiting payment** so the store stays demoable.
