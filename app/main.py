from fastapi import FastAPI

from app.routes.categories import router as categories_router
from app.routes.pictograms import router as pictograms_router
from app.routes.auth import router as auth_router


app = FastAPI(
    title="VOX API",
    description="API para plataforma de Comunicação Aumentativa e Alternativa",
    version="0.1.0",
)


app.include_router(categories_router)
app.include_router(pictograms_router)
app.include_router(auth_router)

@app.get("/")
def root():
    return {
        "message": "Bem-vindo à API do VOX!"
    }
