include .env
export

PORT ?= 8000

# ─── Docker ──────────────────────────────────────────────────────────────────

up:
	docker compose -p sync-mate up -d --build

down:
	docker compose -p sync-mate down

logs:
	docker compose -p sync-mate logs -f

# ─── Local dev ───────────────────────────────────────────────────────────────

dev:
	poetry run uvicorn app.main:app --host 0.0.0.0 --port $(PORT) --reload

# Cloudflare tunnel with named tunnel (token from .env)
tunnel:
	cloudflared tunnel --no-autoupdate run --token $(CLOUDFLARE_TUNNEL_TOKEN)

# Quick temp tunnel (no token needed, gives random *.trycloudflare.com URL)
tunnel-quick:
	cloudflared tunnel --url http://localhost:$(PORT)

# Run uvicorn + cloudflare tunnel together (Ctrl+C stops both)
run:
	@echo "Starting uvicorn and cloudflared tunnel..."
	@trap 'kill 0' INT; \
	poetry run uvicorn app.main:app --host 0.0.0.0 --port $(PORT) & \
	cloudflared tunnel --no-autoupdate run --token $(CLOUDFLARE_TUNNEL_TOKEN) & \
	wait
