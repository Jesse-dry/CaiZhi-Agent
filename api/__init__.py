"""
api/ — FastAPI 后端（未来迁移目标）

当前：Streamlit pages 直接调用 services/workflows
未来：FastAPI endpoints → services/workflows → agents/rag/repositories

目录规划：
    api/
        __init__.py
        main.py              # FastAPI app 入口
        dependencies.py      # Depends() 依赖注入
        routers/
            qa.py            # POST /api/qa/ask
            diagnosis.py     # POST /api/diagnosis/submit
            socratic.py      # POST /api/socratic/judge
            feynman.py       # POST /api/feynman/evaluate
            learning_path.py # POST /api/learning-path/generate
            session.py       # GET/POST /api/session
        middleware/
            cors.py
            auth.py

迁移要点：
1. 用 Pydantic models 替换 schemas/ dataclass（或直接使用 dataclass + TypeAdapter）
2. 用 Depends() 注入 repositories 和 LLM client
3. 用 SSE (Server-Sent Events) 实现流式响应
4. 用 Redis / SQLite 替换 st.session_state

技术栈：
    FastAPI + uvicorn + Pydantic v2 + SSE + Redis + SQLite
"""
