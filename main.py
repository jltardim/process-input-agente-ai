from fastapi import FastAPI
from app.services.agent_factory import agent_factory
# 👇 Importe o router novo
from app.api.webhook import router as webhook_router

app = FastAPI(title="FVK Backend - Python Core")

# 👇 Registre a rota com um prefixo
app.include_router(webhook_router, prefix="/api/v1/webhook", tags=["Webhook"])

@app.get("/")
def health_check():
    return {"status": "online", "message": "Backend Python operante 🚀"}

# ... (mantenha a rota de teste antiga se quiser) ...

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)