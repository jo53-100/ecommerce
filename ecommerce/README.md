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
The site ships English + Spanish. After editing any `{% trans %}` text:
```bash
python manage.py makemessages -l es   # extract new strings into locale/es/.../django.po
# ...edit django.po to add the Spanish text...
python manage.py compilemessages      # compile .po -> .mo  (REQUIRED; Django only reads .mo)
```
> If Spanish “stops working”, it’s almost always a missing `compilemessages`
> step or a server that wasn’t restarted.

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
