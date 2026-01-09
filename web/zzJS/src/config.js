/**
 * web/zzJS/srcconfig.js
 * 全局配置
 */

export const CONFIG = {
    // WebSocket 
    WS_URL: 'ws://localhost:8000/ws',
    ws_STT_URL: 'ws://localhost:8000/ws/stt',
    WS_TTS_URL: 'ws://localhost:8000/ws/tts',

    // 重连策略
    RECONNECT_INTERVAL: 2000,
    MAX_RECONNECT_ATTEMPTS: 5,

    // 音频配置
    AUDIO:{
        SAMPLE_RATE: 16000, // 后端要求的采样率
        BUFFER_SIZE: 4096,  // 处理缓冲区大小
        INPUT_CHANNELS: 1,  //单声道
    }
};

// 枚举状态 - 定义系统可能处于的所有状态
export const APP_STATE = {
    IDLE: 'idle',             // 空闲
    LISTENING: 'listening',   // 正在录音（用户说话中）
    THINKING: 'thinking',     // 正在思考中（等待RAG响应）
    SPEAKING: 'speaking',     // 正在朗读（播放STT）
    ERROR: 'error'            // 发生错误
}

// textGening  这个状态没有设置， 没有意义吗






