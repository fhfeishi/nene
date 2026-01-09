/**
 * web/zzJS/src/app.js
 * 主控制器 - 组装所有模块
 */
import { CONFIG, APP_STATE } from './config.js';
import { StateManager } from './modules/StateManager.js';
import { WebSocketClient } from './modules/WebSocketClient.js';
import { AudioManager } from './modules/AudioManager.js';
import { UIManager } from './modules/UIManager.js';

class App {
    constructor() {
        // 1. 初始化模块
        this.state = new StateManager();
        this.audio = new AudioManager();
        this.ui = new UIManager();
        
        // WebSocket 客户端
        this.wsChat = new WebSocketClient(CONFIG.WS_URL, 'ChatWS');
        this.wsStt = new WebSocketClient(CONFIG.WS_STT_URL, 'SttWS');
        
        // 2. 绑定事件
        this.initBindings();
        
        // 3. 启动连接
        this.wsChat.connect();
    }

    initBindings() {
        // ============ 状态机 UI 响应 ============
        this.state.subscribe((state, payload) => {
            // 根据状态更新 UI，解耦了逻辑
            this.ui.setMicActive(state === APP_STATE.LISTENING);
            
            if (state === APP_STATE.THINKING) {
                this.ui.currentStreamingMessage || this.ui.startAssistantMessage();
            }
        });

        // ============ WebSocket 消息处理 (Chat) ============
        this.wsChat.on('open', () => this.ui.updateConnectionStatus(true));
        this.wsChat.on('close', () => this.ui.updateConnectionStatus(false));
        
        this.wsChat.on('response_start', () => {
            this.state.setState(APP_STATE.THINKING);
            this.ui.startAssistantMessage();
        });

        this.wsChat.on('response_chunk', (data) => {
            this.ui.appendAssistantChunk(data.content);
        });

        this.wsChat.on('audio_chunk', (data) => {
            this.state.setState(APP_STATE.SPEAKING);
            this.audio.enqueueAudio(data.audio);
        });

        this.wsChat.on('response_end', () => {
            this.ui.finishAssistantMessage();
            this.state.setState(APP_STATE.IDLE);
        });

        // ============ WebSocket 消息处理 (STT) ============
        this.wsStt.on('interim', (data) => this.ui.updateVoiceText(data.text));
        
        this.wsStt.on('final', (data) => {
            // 核心逻辑：收到 Final 结果 -> 停止录音 -> 发送给 Chat RAG
            console.log('STT Final:', data.text);
            this.stopListening(); 
            this.handleUserText(data.text); 
        });

        // ============ UI 动作绑定 ============
        this.ui.bindEvents({
            onSend: (text) => this.handleUserText(text),
            onMicToggle: () => this.toggleVoiceInteraction(),
            onStop: () => this.interruptAll() // 打断按钮
        });
    }

    // ============ 核心业务流程 ============

    handleUserText(text) {
        if (!text) return;
        
        // 1. 界面显示用户消息
        this.ui.addUserMessage(text);
        
        // 2. 发送请求给 RAG 后端
        const requestId = Date.now().toString();
        this.wsChat.send({
            type: 'send_message',
            message: text,
            requestId: requestId
        });

        this.state.setState(APP_STATE.THINKING);
    }

    async toggleVoiceInteraction() {
        if (this.state.getState() === APP_STATE.LISTENING) {
            this.stopListening();
        } else {
            // 打断当前的播放
            this.interruptAll();
            this.startListening();
        }
    }

    async startListening() {
        try {
            // 确保 STT 连接就绪
            if (!this.wsStt.isConnected) this.wsStt.connect();

            await this.audio.startRecording((base64PCM) => {
                this.wsStt.send({
                    type: 'audio',
                    audio: base64PCM
                });
            });

            this.wsStt.send({ type: 'start' }); // 告诉后端开始新的识别会话
            this.state.setState(APP_STATE.LISTENING);
            this.ui.updateVoiceText('请说话...');

        } catch (e) {
            console.error('无法启动录音', e);
            alert('麦克风启动失败');
        }
    }

    stopListening() {
        this.audio.stopRecording();
        this.wsStt.send({ type: 'end' });
        this.state.setState(APP_STATE.IDLE);
    }

    // 全局打断（核心鲁棒性功能）
    interruptAll() {
        console.log('🛑 执行打断');
        
        // 1. 停止播放
        this.audio.stopPlayback();
        
        // 2. 停止录音
        if (this.state.getState() === APP_STATE.LISTENING) {
            this.stopListening();
        }

        // 3. 告诉后端停止生成 (可选，看后端是否支持)
        this.wsChat.send({ type: 'stop_generation' });
        
        // 4. UI 复位
        this.ui.finishAssistantMessage();
        this.state.setState(APP_STATE.IDLE);
    }
}

// 启动应用
window.addEventListener('load', () => new App());