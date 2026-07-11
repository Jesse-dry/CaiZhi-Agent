"""
api/routers/ — FastAPI APIRouter 模块。

每个资源一个 router 文件，通过 api/main.py 的 app.include_router() 注册。

路由按资源和操作组织，不按页面映射:

    sessions.py          — CRUD /sessions
    qa.py                — POST  /sessions/{id}/qa-runs
    diagnosis.py         — POST  /sessions/{id}/diagnoses
    socratic.py          — POST  /sessions/{id}/socratic/answers
    feynman.py           — POST  /sessions/{id}/feynman-evaluations
    recommendations.py   — GET   /sessions/{id}/recommendations
    knowledge_graph.py   — GET   /sessions/{id}/knowledge-graph
    runs.py              — GET   /runs/{id}, GET /runs/{id}/events, DELETE /runs/{id}
"""
