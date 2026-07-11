"""
FastAPI 应用入口 — 材智 Agent (CaiZhi) API。

启动:
    uvicorn api.main:app --reload --port 8000

文档:
    http://localhost:8000/docs (Swagger)  /redoc (ReDoc)

API 设计原则:
    围绕资源和操作设计，不围绕页面名称。

    /api/v1
      /sessions                             会话 CRUD
      /sessions/{id}/qa-runs                创建答疑任务
      /sessions/{id}/diagnoses              提交错题诊断
      /sessions/{id}/socratic/answers       提交苏格拉底回答
      /sessions/{id}/feynman-evaluations    提交费曼评价
      /sessions/{id}/recommendations        获取学习路径
      /sessions/{id}/knowledge-graph        获取知识图谱
      /runs/{id}                            查询/删除 run
      /runs/{id}/events                     SSE 事件流
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routers import (
    sessions,
    qa,
    runs,
    diagnosis,
    socratic,
    feynman,
    recommendations,
    knowledge_graph,
)

# ═══════════════════════════════════════════════════════════
# App 创建
# ═══════════════════════════════════════════════════════════

app = FastAPI(
    title="材智 Agent API",
    description="CaiZhi AI Learning Assistant — 材料科学智能学习助手",
    version="0.2.0",
)

# ═══════════════════════════════════════════════════════════
# 中间件
# ═══════════════════════════════════════════════════════════

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ═══════════════════════════════════════════════════════════
# 路由注册
# ═══════════════════════════════════════════════════════════

app.include_router(sessions.router)           # CRUD /sessions
app.include_router(qa.router)                 # POST /sessions/{id}/qa-runs
app.include_router(diagnosis.router)          # POST /sessions/{id}/diagnoses
app.include_router(socratic.router)           # POST /sessions/{id}/socratic/answers
app.include_router(feynman.router)            # POST /sessions/{id}/feynman-evaluations
app.include_router(recommendations.router)    # GET  /sessions/{id}/recommendations
app.include_router(knowledge_graph.router)    # GET  /sessions/{id}/knowledge-graph
app.include_router(runs.router)               # GET/DELETE /runs/{id} + events

# ═══════════════════════════════════════════════════════════
# 健康检查
# ═══════════════════════════════════════════════════════════

@app.get("/api/health", tags=["System"])
async def health():
    """服务健康检查"""
    return {"status": "ok", "version": "0.2.0"}


# ═══════════════════════════════════════════════════════════
# 启动入口
# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.main:app", host="0.0.0.0", port=8000, reload=True)
