# 支持语音的rag系统 nene

1. 功能
    a. 支持RAG。
      - 知识库：切换、管理 等等， todo
      - 文本知识库
    b. 支持对话模式1：普通模式。
      - tts：云端TTS（edgetts、API）、本地TTS
      - stt：云端STT（API）、本地STT
      - HTTP POST, 支持用户输入文本\语音，系统返回文本， 答案文本可以朗读。
    c.模式2：语音童话模式。
      - WebSocket/SocketIO, 持续的语音对话。
    d. 支持灵动 UI
      - 主UI主题切换，包括暗黑主题和亮主题。
      - 语音通话UI
    e. 支持聊天记录功能
      - todo
    f. 支持系统设置
      - todo
2. 前后端职能分配

```python
nene/  # 语音RAG
│
├── app/                       # FastAPI后端部分 （未完善）
│   ├── core/                  # [核心] 全局共享的基础设施
│   │   ├── config.py          # 环境变量配置 (Pydantic Settings)
│   │   ├── exceptions.py      # 自定义异常
│   │   └── logger.py          # 统一日志配置
│   ├── schemas/               # [协议] 前后端交互的数据模型 (Pydantic)
│   │   ├── protocol.py        # 定义 WS 消息格式 (type, payload)
│   │   └── chat.py            # 定义 Chat 相关的输入输出模型
│   ├── components/
│   │       ├── ingestdb/
│   │       │      ├── component.py    # 工程组件（现在就需要应用的代码）
│   │       │      └── api.py          # 集成为api zzIngestDB （可能未来用得上，再比如测试之类的）
│   │       ├── rag/
│   │       │      ├── component.py
│   │       │      └── api.py          # class zzrag
│   │       ├── stt/
│   │       │      ├── component.py
│   │       │      └── api.py          # class zztts
│   │       ├── tts/
│   │       │      ├── component.py
│   │       │      └── api.py          # class zztts
│   │       ├── api.py   
│   │       └── base.py
│   │
│   ├── routers/               # [路由] API 路由定义
│   │    ├── websocket.py
│   │    └── api.py
│   ├── config.py
│   ├── coonstants.py            # root_dir, db_dir ..
│   └── server.py
├── datas/
│   ├── data_db/
│   │       ├── chroma_db/
│   │       ├── qdrant_db/
│   │       ├── postgreSQL_db/
│   │       └── milvus_db/  # docker部署好一些？
│   └── docs/     # 文档
├── scripts/      # 脚本， 启动脚本、测试脚本
├── web/
│   ├── AgentStudio/                 # 前端部分 （仅仅完善了基础的UI，功能未完善）
│   │       ├── src/ 
│   │       │   ├── assets/
│   │       │   ├── features/
│   │       │   ├── hooks/
│   │       │   ├── services/
│   │       │   ├── store/
│   │       │   ├── types/
│   │       │   ├── App.css
│   │       │   ├── App.tsx
│   │       │   ├── index.css
│   │       │   ├── main.tsx
│   │       ├── index.html
│   │       ├── package.json
│   │       ├── xx.config.js
│   │       ├── ..

│   ├── zzVUE/     # todo
```

```text
graph TD
    User((用户))
    
    subgraph Frontend_JS ["前端 (JavaScript)"]
        UI[UI View Layer]
        SM[State Machine (状态机)]
        AM[Audio Manager (录音/播放)]
        WS[WS Client (网络层)]
    end
    
    subgraph Backend_PY ["后端 (Python/FastAPI)"]
        API[FastAPI Router]
        CM[Connection Manager]
        
        subgraph Services
            STT[STT Service (VAD/ASR)]
            RAG[RAG Service (LLM/Retriever)]
            TTS[TTS Service (Stream Synthesizer)]
        end
        
        Queue[Async Queues]
    end

    User <-->|麦克风/扬声器| AM
    AM <-->|PCM Stream| WS
    UI <-->|Events| SM
    SM <-->|Control| WS
    WS <-->|WebSocket Protocol| API
    
    API <--> CM
    API -->|Audio| STT
    STT -->|Text| RAG
    RAG -->|Text Stream| TTS
    TTS -->|Audio Stream| Queue
    Queue -->|Bytes| API

```
