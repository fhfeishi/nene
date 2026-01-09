# 支持语音的rag系统 nene

```python
nene/  # 语音RAG
│
├── app/
│   ├── __init__.py
│   │
│   ├── core/                  # [核心] 全局共享的基础设施
│   │   ├── config.py          # 环境变量配置 (Pydantic Settings)
│   │   ├── exceptions.py      # 自定义异常
│   │   └── logger.py          # 统一日志配置
│   │
│   ├── schemas/               # [协议] 前后端交互的数据模型 (Pydantic)
│   │   ├── protocol.py        # 定义 WS 消息格式 (type, payload)
│   │   └── chat.py            # 定义 Chat 相关的输入输出模型
│   │
│   ├── components/
│   │       ├── __init__.py
│   │       ├── ingestdb/
│   │       │      ├── __init__.py
│   │       │      ├── component.py    # 工程组件（现在就需要应用的代码）
│   │       │      └── api.py          # 集成为api （可能未来用得上，再比如测试之类的）
│   │       ├── rag/
│   │       │      ├── __init__.py
│   │       │      ├── component.py
│   │       │      └── api.py
│   │       ├── stt/
│   │       │      ├── __init__.py
│   │       │      ├── component.py
│   │       │      └── api.py
│   │       ├── tts/
│   │       │      ├── __init__.py
│   │       │      ├── component.py
│   │       │      └── api.py   
│   │       └── base.py
│   │
│   ├── routers/               # [路由] API 路由定义
│   │    ├── websocket.py
│   │    └── api.py
│   │
│   ├── config.py
│   ├── coonstants.py
│   └── server.py
├── datas/
│   ├── data_db/
│   │       ├── chroma_db/
│   │       └── pymilvus_db/
│   └── docs/
├── scripts/
│   ├── start.py
│   ├── test_xx.py
│   └── ...
├── web/
│   ├── zzJS/
│   │      ├── modules/ *.js
│   │      ├── app.js
│   │      └── app_old.js
│   ├── zzReact/   # todo
│   ├── zzVUE/     # todo
│   └── ...
├── zztest/
│   ├── xx
│   └── 

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

