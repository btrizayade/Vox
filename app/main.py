from fastapi import FastAPI

app = FastAPI(
    title="Comuni+ API",
    description="API para plataforma de Comunicação Aumentativa e Alternativa",
    version="0.1.0",
)


@app.get("/")
def root():
    return {
        "message": "Bem-vindo à API do Comuni+!"
    }