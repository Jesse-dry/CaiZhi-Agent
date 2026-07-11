"""
FastAPI 应用入口（占位）

未来实现：
    from fastapi import FastAPI
    from api.routers import qa, diagnosis, socratic, feynman, learning_path

    app = FastAPI(title="材智 Agent API", version="0.2.0")

    app.include_router(qa.router, prefix="/api/qa", tags=["智能答疑"])
    app.include_router(diagnosis.router, prefix="/api/diagnosis", tags=["错题诊断"])
    app.include_router(socratic.router, prefix="/api/socratic", tags=["苏格拉底引导"])
    app.include_router(feynman.router, prefix="/api/feynman", tags=["费曼评价"])
    app.include_router(learning_path.router, prefix="/api/learning-path", tags=["学习路径"])

    @app.get("/api/health")
    async def health():
        return {"status": "ok"}
"""
