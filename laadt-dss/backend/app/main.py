from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes import simulation, chat, iot, dt, network, pv_system, bess_system, advisor, geo
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(key_func=get_remote_address, default_limits=["60/minute"])

app = FastAPI(
    title="LAaDT-DSS API",
    description="LLM-Augmented Adaptive Digital Twin - Decision Support System",
    version="1.0.0"
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(simulation.router)
app.include_router(chat.router)
app.include_router(iot.router)
app.include_router(dt.router)
app.include_router(network.router)
app.include_router(pv_system.router)
app.include_router(bess_system.router)
app.include_router(advisor.router)
app.include_router(geo.router)

@app.get("/health")
def health_check():
    return {"status": "ok", "message": "LAaDT-DSS API is running"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)

