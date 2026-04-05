# Auth0 Proxy Starter (`oauth2-proxy` + `nginx`)

This starter protects both:

- Taipy GUI (`main.py`) on `localhost:5000`
- Taipy REST (`rest_main.py`) on `localhost:5001` via `/api/*`

## 1) Prepare env file

```bash
cp deploy/auth-proxy/.env.auth-proxy.example deploy/auth-proxy/.env.auth-proxy
make proxy-cookie-secret
```

Put the generated secret in `OAUTH2_PROXY_COOKIE_SECRET`.

Set Auth0 values in `deploy/auth-proxy/.env.auth-proxy`:

- `AUTH0_DOMAIN`
- `AUTH0_CLIENT_ID`
- `AUTH0_CLIENT_SECRET`
- `AUTH_PROXY_REDIRECT_URL`

For the minimal passwordless flow, use an Auth0 **Regular Web Application**
for `oauth2-proxy`, then enable **Authentication → Passwordless → Email**
with **OTP** delivery in your Auth0 tenant. Make sure the application is
allowed to use that passwordless email connection via Universal Login.

Auth0 callback URL must match:

- `http://localhost:8080/oauth2/callback`

Recommended Auth0 tenant settings for this stack:

- Allowed Callback URLs: `http://localhost:8080/oauth2/callback`
- Allowed Logout URLs: `http://localhost:8080`
- Allowed Web Origins: `http://localhost:8080`
- Authentication Profile: Universal Login
- Passwordless connection: Email + OTP enabled for this application

Important: `oauth2-proxy` is still doing standard OIDC. Passwordless OTP is
handled by Auth0's hosted login experience, so no Taipy app code changes are
required just to send an email OTP at login.

## 2) Run Taipy services locally

```bash
# Terminal A
taipy run main.py

# Terminal B
TAIPY_PORT=5001 taipy run rest_main.py
```

## 3) Start proxy stack

```bash
make auth-proxy-up
```

Open:

- `http://localhost:8080/` for GUI
- `http://localhost:8080/api/` for REST root

Expected flow:

1. Visit `http://localhost:8080/`
2. `oauth2-proxy` redirects to Auth0 Universal Login
3. User enters email and receives a one-time code
4. After OTP verification, Auth0 redirects back to `/oauth2/callback`
5. `oauth2-proxy` sets the authenticated session cookie and forwards trusted
   identity headers to the app

## 4) Stop stack

```bash
make auth-proxy-down
```
