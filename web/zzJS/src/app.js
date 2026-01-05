// ============================================================================
// web/src/app.js - 博物馆RAG语音交互系统前端
// ============================================================================
// 
// 核心修复：
// 1. STT 触发源统一：只依赖后端 VAD 发送的 final 结果触发发送
// 2. 移除前端静音检测发送逻辑，避免重复触发
// 3. DOM 引用管理：使用 currentStreamingMessage 防止消息气泡错乱
// 4. TTS 架构：使用后端流式 TTS，前端只负责播放
//
// ============================================================================

class StreamingMessageManager{
    /**
     * 流式消息管理器
     * 职责：管理流式消息的创建、更新、完成，与外部状态解耦
     */
}






class MuseumChatApp {
    constructor() {
        // ====================================================================
        // 一、基础状态
        // ====================================================================
        this.socket = null;                      // WebSocket连接
        this.isConnected = false;                // 连接状态
        this.chatHistory = [];                   // 聊天历史
        
        // ====================================================================
        // 二、语音识别(STT)相关状态
        // ====================================================================
        this.realtimeRecognition = null;         // STT WebSocket连接
        this.mediaRecorder = null;               // MediaRecorder实例
        this.audioContext = null;                // AudioContext实例
        this.audioSource = null;                 // 音频源节点
        this.processor = null;                   // 音频处理节点
        this.audioStream = null;                 // 麦克风音频流
        this.pcmBuffer = [];                     // PCM数据缓冲区
        this.audioChunks = [];                   // 音频块缓冲区
        
        this.isMicrophoneActive = false;         // 麦克风是否激活
        this.isVoiceActive = false;              // 语音会话是否激活
        this.streamingSessionActive = false;     // 流式识别会话是否激活
        this.isVoiceMode = false;                // 是否处于语音通话模式（用于自动TTS）
        
        this.recognizedText = '';                // 当前识别结果（实时显示）
        this.finalResults = [];                  // 累积的final识别结果
        this.lastSendTime = 0;                   // 上次发送音频时间
        this.lastRecognitionTime = 0;            // 上次识别到内容时间
        
        this.recognitionTimeout = null;          // 识别超时定时器（UI用）
        this.hasSentCurrentRecognition = false;  // 当前识别会话是否已发送（核心防重复标志）
        
        // ====================================================================
        // 三、语音合成(TTS)相关状态
        // ====================================================================
        this.ttsWebSocket = null;                // TTS WebSocket连接
        this.currentAudio = null;                // 当前播放的Audio对象
        this.audioQueue = [];                    // 音频播放队列
        this.isPlayingQueue = false;             // 是否正在播放队列
        this.isQueueClosing = false;             // 队列是否正在关闭
        this.hasStreamedTTS = false;             // 是否已使用流式TTS
        
        // 流式TTS专用状态
        this.streamingTTSBuffer = '';            // 流式TTS文本缓冲区
        this.streamingTTSRequestId = null;       // 当前流式TTS请求ID
        this.isStreamingTTSActive = false;       // 是否正在流式TTS
        this.streamingTTSSentenceQueue = [];     // 流式TTS句子队列
        this.isProcessingTTSSentence = false;    // 是否正在处理TTS句子
        this.currentTTSRequestId = null;         // 当前TTS请求ID（用于取消旧TTS）
        
        // ====================================================================
        // 四、响应生成控制状态
        // ====================================================================
        this.shouldIgnoreResponse = false;       // 是否忽略响应（用于停止/打断）
        this.isGeneratingResponse = false;       // 是否正在生成RAG响应
        this.currentResponseRequestId = null;    // 当前响应请求ID
        this.currentStreamingMessage = null;     // 当前流式消息DOM引用
        
        // ====================================================================
        // 五、初始化
        // ====================================================================
        this.init();
    }

    // ========================================================================
    // 初始化方法
    // ========================================================================
    
    init() {
        this.initializeSocket();
        this.initializeElements();
        this.initializeEventListeners();
        this.updateConnectionStatus('connecting');
    }

    /**
     * 初始化WebSocket连接和事件处理
     */
    initializeSocket() {
        this.socket = new WebSocket('ws://localhost:8000/ws');
        
        this.socket.onopen = () => {
            console.log('✅ [Socket] 连接到服务器成功');
            this.isConnected = true;
            this.updateConnectionStatus('connected');
            this.hideLoading();
        };
        
        this.socket.onclose = () => {
            console.log('❌ [Socket] 与服务器断开连接');
            this.isConnected = false;
            this.updateConnectionStatus('disconnected');
        };

        this.socket.onerror = (error) => {
            console.error('❌ [Socket] 连接错误:', error);
            this.updateConnectionStatus('disconnected');
        };

        // 统一消息处理
        this.socket.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                console.log('📨 [Socket] 收到消息:', data.type);
                
                switch (data.type) {
                    case 'response_start':
                        this.handleResponseStart(data);
                        break;
                    case 'response_chunk':
                        this.handleResponseChunk(data);
                        break;
                    case 'response_end':
                        this.handleResponseEnd(data);
                        break;
                    case 'audio_chunk':
                        this.handleAudioChunk(data);
                        break;
                    case 'error':
                        this.handleError(data);
                        break;
                    default:
                        console.log('⚠️ [Socket] 未知消息类型:', data.type);
                }
            } catch (e) {
                console.error('❌ [Socket] 解析消息失败:', e, event.data);
            }
        };
    }

    // ========================================================================
    // RAG响应处理
    // ========================================================================

    /**
     * 处理响应开始事件
     */
    handleResponseStart(data) {
        const requestId = data.requestId || null;
        console.log('🚀 [response_start] requestId:', requestId);
        
        // 检查是否是当前请求的响应
        if (requestId && requestId !== this.currentResponseRequestId) {
            console.log('⏭️ [忽略] 收到旧请求的响应，忽略');
            return;
        }

        // 清理所有旧的流式消息
        this.cleanupAllStreamingMessages();
        
        // 重置状态
        this.shouldIgnoreResponse = false;
        this.isGeneratingResponse = true;
        
        // 语音模式：准备接收后端流式TTS音频
        if (this.isVoiceMode) {
            console.log('🎤 [语音模式] 准备接收流式TTS音频');
            this.streamingTTSRequestId = requestId;
            this.streamingTTSBuffer = '';
            this.isStreamingTTSActive = false;
            
            this.showAudioControls();
            this.audioQueue = [];
            this.isPlayingQueue = false;
        }
        
        this.showTypingIndicator();
        // 保存流式消息DOM引用
        this.currentStreamingMessage = this.addMessage('assistant', '', true);
    }

    /**
     * 清理所有旧的流式消息
     */
    cleanupAllStreamingMessages() {
        const streamingMessages = this.elements.chatMessages.querySelectorAll('.message[data-streaming="true"]');
        
        streamingMessages.forEach(msg => {
            const textDiv = msg.querySelector('.message-text');
            const currentText = msg.dataset.rawText || '';
            
            if (currentText) {
                textDiv.innerHTML = this.formatMessageContent(currentText);
                const actions = this.createMessageActions(currentText);
                msg.querySelector('.message-content').appendChild(actions);
            } else {
                msg.remove();
            }
            
            delete msg.dataset.streaming;
            delete msg.dataset.rawText;
        });
        
        if (streamingMessages.length > 0) {
            console.log(`🧹 [清理] 清理了 ${streamingMessages.length} 个旧的流式消息`);
        }
    }

    /**
     * 处理响应块事件（流式文本）
     */
    handleResponseChunk(data) {
        const requestId = data.requestId || null;
        
        if (requestId && requestId !== this.currentResponseRequestId) {
            console.log('⏭️ [忽略] 收到旧请求的响应块');
            return;
        }
        
        if (this.shouldIgnoreResponse) {
            console.log('⏭️ [忽略] 用户已停止');
            return;
        }
        
        // 更新文字显示
        this.updateLastMessage(data.content, data.isFirst);
        
        // 标记流式TTS已激活（后端会发送audio_chunk）
        if (this.isVoiceMode || data.autoTTS) {
            this.isStreamingTTSActive = true;
            this.streamingTTSRequestId = requestId;
        }
    }

    /**
     * 处理响应结束事件
     */
    handleResponseEnd(data) {
        const requestId = data.requestId || null;
        
        if (requestId && requestId !== this.currentResponseRequestId) {
            console.log('⏭️ [忽略] 收到旧请求的响应结束');
            return;
        }
        
        if (this.shouldIgnoreResponse) {
            console.log('⏭️ [忽略] 用户已停止');
            this.hideTypingIndicator();
            this.isGeneratingResponse = false;
            this.cleanupStreamingMessage();
            return;
        }
        
        this.isGeneratingResponse = false;
        this.hideTypingIndicator();
        this.finalizeLastMessage(data.fullResponse);

        console.log('📊 [response_end] 状态:', {
            isVoiceMode: this.isVoiceMode,
            isStreamingTTSActive: this.isStreamingTTSActive
        });
        
        // 后端流式TTS：等待音频播放完成
        if (this.isStreamingTTSActive) {
            console.log('✅ [流式TTS] 后端音频已全部接收，等待播放完成');
            this.isStreamingTTSActive = false;
            this.streamingTTSRequestId = null;
            
            const checkAndHide = () => {
                if (!this.isPlayingQueue && this.audioQueue.length === 0) {
                    this.hideAudioControls();
                } else {
                    setTimeout(checkAndHide, 500);
                }
            };
            setTimeout(checkAndHide, 1000);
        }
        // 非流式模式回退
        else if (!this.shouldIgnoreResponse && data.fullResponse && this.isVoiceMode) {
            console.log('🎤 [自动播放] 使用非流式模式播放');
            const ttsRequestId = Date.now();
            this.currentTTSRequestId = ttsRequestId;
            this.speakText(data.fullResponse, ttsRequestId);
        }

        // 重置状态，允许下一次语音输入
        this.isVoiceMode = false;
        this.isVoiceActive = false;
        this.hasSentCurrentRecognition = false;  // 关键：允许下一次发送
    }

    /**
     * 处理音频块事件（后端流式TTS）
     */
    handleAudioChunk(data) {
        if (this.shouldIgnoreResponse) {
            console.log('⏭️ [忽略] 用户已停止，丢弃音频');
            return;
        }
        
        if (data.audio) {
            this.enqueueAudioChunk(data.audio);
        }
    }

    /**
     * 处理错误事件
     */
    handleError(data) {
        console.error('❌ [Socket] 服务器错误:', data.message);
        this.hideTypingIndicator();
        this.isGeneratingResponse = false;
        this.hasSentCurrentRecognition = false;
        this.showError(data.message || '服务器错误');
    }

    /**
     * 初始化DOM元素引用
     */
    initializeElements() {
        this.elements = {
            chatMessages: document.getElementById('chatMessages'),
            messageInput: document.getElementById('messageInput'),
            sendBtn: document.getElementById('sendBtn'),
            micBtn: document.getElementById('micBtn'),
            stopBtn: document.getElementById('stopBtn'),
            clearChat: document.getElementById('clearChat'),
            typingIndicator: document.getElementById('typingIndicator'),
            voiceStatus: document.getElementById('voiceStatus'),
            connectionStatus: document.getElementById('connectionStatus'),
            loadingOverlay: document.getElementById('loadingOverlay'),
            errorModal: document.getElementById('errorModal'),
            errorMessage: document.getElementById('errorMessage'),
            closeErrorModal: document.getElementById('closeErrorModal'),
            confirmError: document.getElementById('confirmError'),
            audioControls: document.getElementById('audioControls'),
            pauseAudio: document.getElementById('pauseAudio'),
            stopAudio: document.getElementById('stopAudio'),
            charCount: document.querySelector('.char-count'),
            voiceRecognitionArea: document.getElementById('voiceRecognitionArea'),
            voiceRecognitionText: document.getElementById('voiceRecognitionText')
        };
    }

    /**
     * 初始化事件监听器
     */
    initializeEventListeners() {
        // 发送消息
        this.elements.sendBtn.addEventListener('click', () => this.sendMessage());
        this.elements.messageInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.sendMessage();
            }
        });

        // 输入框自动调整高度
        this.elements.messageInput.addEventListener('input', (e) => {
            this.autoResizeTextarea(e.target);
            this.updateCharCount();
        });

        // 麦克风按钮
        this.elements.micBtn.addEventListener('click', () => this.toggleMicrophone());
        
        // 停止按钮
        this.elements.stopBtn.addEventListener('click', () => this.stopGeneration());
        
        // 清空对话
        this.elements.clearChat.addEventListener('click', () => this.clearChat());

        // 建议问题点击
        document.querySelectorAll('.chip').forEach(chip => {
            chip.addEventListener('click', (e) => {
                const question = e.target.getAttribute('data-question');
                this.elements.messageInput.value = question;
                this.sendMessage();
            });
        });

        // 错误模态框
        this.elements.closeErrorModal.addEventListener('click', () => this.hideError());
        this.elements.confirmError.addEventListener('click', () => this.hideError());
        this.elements.errorModal.addEventListener('click', (e) => {
            if (e.target === this.elements.errorModal) {
                this.hideError();
            }
        });

        // 音频控制
        this.elements.pauseAudio.addEventListener('click', () => this.pauseAudio());
        this.elements.stopAudio.addEventListener('click', () => this.stopAudio());
    }

    // ========================================================================
    // 第一部分：语音识别(STT)模块
    // ========================================================================

    /**
     * 切换麦克风状态
     */
    toggleMicrophone() {
        if (this.isMicrophoneActive || this.streamingSessionActive) {
            console.log('🛑 [切换] 停止录音和语音识别');
            this.stopMicrophone();
        } else {
            console.log('🎤 [切换] 启动录音和语音识别');
            if (!this.realtimeRecognition || this.realtimeRecognition.readyState !== WebSocket.OPEN) {
                this.startContinuousRecognition();
            } else {
                this.startMicrophone();
            }
        }
    }

    /**
     * 启动持续语音识别
     */
    async startContinuousRecognition() {
        try {
            console.log('🎤 [常开模式] 启动持续语音识别...');
            
            await this.initializeRealtimeSpeechRecognition();
            
            let waitCount = 0;
            while (this.realtimeRecognition && 
                   this.realtimeRecognition.readyState === WebSocket.CONNECTING && 
                   waitCount < 30) {
                await new Promise(resolve => setTimeout(resolve, 100));
                waitCount++;
            }
            
            if (!this.realtimeRecognition || this.realtimeRecognition.readyState !== WebSocket.OPEN) {
                console.error('❌ [常开模式] WebSocket连接失败');
                this.showError('语音识别服务连接失败，请确认后端服务器已启动');
                return;
            }
            
            this.realtimeRecognition.send(JSON.stringify({ type: 'start' }));
            console.log('🚀 [常开模式] 已发送流式识别start指令');
            this.streamingSessionActive = true;
            
            await this.startMicrophone();
            
            console.log('✅ [常开模式] 持续语音识别已启动');
        } catch (error) {
            console.error('❌ [常开模式] 启动失败:', error);
            this.showError('启动语音识别失败: ' + error.message);
        }
    }

    /**
     * 初始化实时语音识别WebSocket连接
     */
    async initializeRealtimeSpeechRecognition() {
        try {
            if (this.realtimeRecognition && this.realtimeRecognition.readyState === WebSocket.OPEN) {
                console.log('WebSocket已连接，无需重复建立');
                return true;
            }
            
            if (this.realtimeRecognition && this.realtimeRecognition.readyState === WebSocket.CONNECTING) {
                console.log('WebSocket正在连接中...');
                return true;
            }
            
            console.log('正在建立WebSocket连接...');
            this.realtimeRecognition = new WebSocket('ws://localhost:8000/ws/realtime-speech');
            
            this.realtimeRecognition.onopen = () => {
                console.log('✅ 实时语音识别连接已建立');
                this.streamingSessionActive = false;
            };

            this.realtimeRecognition.onmessage = (event) => {
                const data = JSON.parse(event.data);
                console.log('📨 [STT] 收到消息:', data.type, data.text ? data.text.substring(0, 30) : '');
                this.handleRealtimeSpeechResult(data);
            };

            this.realtimeRecognition.onerror = (error) => {
                console.error('❌ 实时语音识别连接错误:', error);
            };

            this.realtimeRecognition.onclose = () => {
                console.log('实时语音识别连接已关闭');
                if (this.isVoiceActive) {
                    console.log('🔄 语音会话仍在进行，自动重连...');
                    setTimeout(() => {
                        this.initializeRealtimeSpeechRecognition().catch(err => {
                            console.error('❌ 自动重连失败:', err);
                        });
                    }, 500);
                } else {
                    this.realtimeRecognition = null;
                }
            };

            await this.initializeAudioRecording();
            
            return true;
        } catch (error) {
            console.error('初始化实时语音识别失败:', error);
            return false;
        }
    }

    /**
     * 初始化音频录制
     */
    async initializeAudioRecording() {
        try {
            if (this.audioStream) {
                this.audioStream.getTracks().forEach(track => track.stop());
            }
            
            const stream = await navigator.mediaDevices.getUserMedia({
                audio: {
                    sampleRate: 16000,
                    channelCount: 1,
                    echoCancellation: true,
                    noiseSuppression: true
                }
            });

            this.audioStream = stream;

            this.mediaRecorder = new MediaRecorder(stream, {
                mimeType: 'audio/webm;codecs=opus'
            });

            this.audioChunks = [];

            this.audioContext = new (window.AudioContext || window.webkitAudioContext)();
            this.audioSource = this.audioContext.createMediaStreamSource(stream);
            this.processor = this.audioContext.createScriptProcessor(4096, 1, 1);
            
            this.pcmBuffer = [];
            this.lastSendTime = 0;
            
            const sourceSampleRate = this.audioContext.sampleRate;
            const targetSampleRate = 16000;
            const needsResample = sourceSampleRate !== targetSampleRate;
            
            console.log(`🎵 AudioContext采样率: ${sourceSampleRate}Hz, 目标: ${targetSampleRate}Hz`);
            
            const pcmToBase64 = (pcm16Array) => {
                const pcmArray = new Uint8Array(pcm16Array.buffer);
                let binaryString = '';
                const chunkSize = 8192;
                for (let i = 0; i < pcmArray.length; i += chunkSize) {
                    const chunk = pcmArray.subarray(i, Math.min(i + chunkSize, pcmArray.length));
                    binaryString += String.fromCharCode.apply(null, chunk);
                }
                return btoa(binaryString);
            };
            
            this.processor.onaudioprocess = (event) => {
                if (!this.isMicrophoneActive) return;

                const inputData = event.inputBuffer.getChannelData(0);
                let processedData = inputData;
                
                if (needsResample) {
                    const targetLength = Math.floor(inputData.length * targetSampleRate / sourceSampleRate);
                    processedData = new Float32Array(targetLength);
                    
                    for (let i = 0; i < targetLength; i++) {
                        const srcIndex = (i * sourceSampleRate) / targetSampleRate;
                        const srcIndexFloor = Math.floor(srcIndex);
                        const srcIndexCeil = Math.min(srcIndexFloor + 1, inputData.length - 1);
                        const fraction = srcIndex - srcIndexFloor;
                        processedData[i] = inputData[srcIndexFloor] * (1 - fraction) + inputData[srcIndexCeil] * fraction;
                    }
                }
                
                const pcm16 = new Int16Array(processedData.length);
                for (let i = 0; i < processedData.length; i++) {
                    const sample = Math.max(-1, Math.min(1, processedData[i]));
                    pcm16[i] = sample < 0 ? sample * 0x8000 : sample * 0x7FFF;
                }
                
                this.pcmBuffer.push(pcm16);
                
                const now = Date.now();
                if (now - this.lastSendTime >= 100 && 
                    this.realtimeRecognition && 
                    this.realtimeRecognition.readyState === WebSocket.OPEN && 
                    this.streamingSessionActive) {
                    
                    const totalLength = this.pcmBuffer.reduce((sum, arr) => sum + arr.length, 0);
                    if (totalLength > 0) {
                        const combinedPCM = new Int16Array(totalLength);
                        let offset = 0;
                        for (const arr of this.pcmBuffer) {
                            combinedPCM.set(arr, offset);
                            offset += arr.length;
                        }
                        this.pcmBuffer = [];
                        
                        const base64Audio = pcmToBase64(combinedPCM);
                        
                        try {
                            this.realtimeRecognition.send(JSON.stringify({
                                type: 'audio',
                                audio: base64Audio
                            }));
                            this.lastSendTime = now;
                        } catch (error) {
                            console.error('❌ 发送音频数据失败:', error);
                        }
                    }
                }
            };
            
            this.audioSource.connect(this.processor);
            this.processor.connect(this.audioContext.destination);
            
            this.mediaRecorder.ondataavailable = (event) => {
                if (event.data.size > 0) {
                    this.audioChunks.push(event.data);
                }
            };

            this.mediaRecorder.onstop = async () => {
                console.log('🎙️ 录音停止');
                this.hideVoiceRecognitionArea();
                
                if (this.processor) {
                    try { this.processor.disconnect(); } catch (e) {}
                }
                if (this.audioSource) {
                    try { this.audioSource.disconnect(); } catch (e) {}
                }
                
                if (this.pcmBuffer.length > 0 && 
                    this.realtimeRecognition && 
                    this.realtimeRecognition.readyState === WebSocket.OPEN) {
                    try {
                        const totalLength = this.pcmBuffer.reduce((sum, arr) => sum + arr.length, 0);
                        const combinedPCM = new Int16Array(totalLength);
                        let offset = 0;
                        for (const arr of this.pcmBuffer) {
                            combinedPCM.set(arr, offset);
                            offset += arr.length;
                        }
                        this.pcmBuffer = [];
                        
                        const base64Audio = pcmToBase64(combinedPCM);
                        this.realtimeRecognition.send(JSON.stringify({
                            type: 'audio',
                            audio: base64Audio
                        }));
                    } catch (error) {
                        console.error('❌ 发送最后音频数据失败:', error);
                    }
                }
                
                if (this.realtimeRecognition && this.realtimeRecognition.readyState === WebSocket.OPEN) {
                    this.realtimeRecognition.send(JSON.stringify({ type: 'end' }));
                    this.streamingSessionActive = false;
                }
                
                this.audioChunks = [];
            };

            console.log('✅ 音频录制初始化成功');
        } catch (error) {
            console.error('❌ 音频录制初始化失败:', error);
            this.showError('无法访问麦克风，请检查权限设置');
        }
    }

    /**
     * 启动麦克风录音
     */
    async startMicrophone() {
        try {
            console.log('🎤 开始启动麦克风...');
            
            this.stopAudio();
            
            if (!this.realtimeRecognition || this.realtimeRecognition.readyState !== WebSocket.OPEN) {
                console.log('🔌 建立语音识别连接...');
                await this.initializeRealtimeSpeechRecognition();
                
                let waitCount = 0;
                while (this.realtimeRecognition && 
                       this.realtimeRecognition.readyState === WebSocket.CONNECTING && 
                       waitCount < 30) {
                    await new Promise(resolve => setTimeout(resolve, 100));
                    waitCount++;
                }
                
                if (!this.realtimeRecognition || this.realtimeRecognition.readyState !== WebSocket.OPEN) {
                    this.showError('语音识别服务连接失败，请确认后端服务器已启动');
                    return;
                }
            }
            
            const needsReinit = !this.mediaRecorder || 
                               !this.audioContext || 
                               !this.processor || 
                               !this.audioSource ||
                               this.audioContext.state === 'closed';
            
            if (needsReinit) {
                console.log('⚠️ 音频资源不完整，重新初始化...');
                this.cleanupAudioResources();
                await this.initializeAudioRecording();
            }
            
            if (!this.mediaRecorder) {
                this.showError('麦克风初始化失败，请检查浏览器权限');
                return;
            }

            this.isVoiceActive = true;

            if (this.audioSource && this.processor) {
                try { this.audioSource.disconnect(); } catch (e) {}
                try { this.processor.disconnect(); } catch (e) {}
                try {
                    this.audioSource.connect(this.processor);
                    this.processor.connect(this.audioContext.destination);
                } catch (e) {
                    console.error('❌ 重新连接AudioContext节点失败:', e);
                }
            }

            if (this.realtimeRecognition && this.realtimeRecognition.readyState === WebSocket.OPEN) {
                try {
                    this.realtimeRecognition.send(JSON.stringify({ type: 'start' }));
                    this.streamingSessionActive = true;
                } catch (err) {
                    console.error('❌ 发送start指令失败:', err);
                }
            }

            if (!this.isMicrophoneActive) {
                this.recognizedText = '';
                this.finalResults = [];
                this.elements.messageInput.value = '';
                this.updateCharCount();
                this.hasSentCurrentRecognition = false;
            }
            
            if (!this.isMicrophoneActive) {
                this.startRecording();
                this.elements.voiceRecognitionText.textContent = '请开始说话...';
                this.elements.voiceRecognitionArea.style.display = 'block';
                this.elements.voiceRecognitionArea.classList.add('listening');
            }
            
            console.log('✅ 麦克风启动完成');
        } catch (error) {
            console.error('❌ 启动录音失败:', error);
            this.showError('录音启动失败：' + error.message);
        }
    }

    /**
     * 停止麦克风录音
     */
    stopMicrophone() {
        console.log('🛑 停止麦克风...');
        
        if (this.mediaRecorder && this.isMicrophoneActive) {
            this.stopRecording();
        }
        
        this.stopContinuousRecognition();
        
        this.isMicrophoneActive = false;
        this.streamingSessionActive = false;
        this.isVoiceActive = false;
        
        this.updateMicrophoneButton();
    }

    /**
     * 停止持续语音识别
     */
    stopContinuousRecognition() {
        console.log('🛑 停止持续语音识别...');
        
        if (this.realtimeRecognition && this.realtimeRecognition.readyState === WebSocket.OPEN) {
            try {
                this.realtimeRecognition.send(JSON.stringify({ type: 'end' }));
            } catch (err) {
                console.error('❌ 发送结束信号失败:', err);
            }
        }
        
        if (this.realtimeRecognition) {
            try {
                this.realtimeRecognition.onopen = null;
                this.realtimeRecognition.onmessage = null;
                this.realtimeRecognition.onerror = null;
                this.realtimeRecognition.onclose = null;
                
                if (this.realtimeRecognition.readyState === WebSocket.OPEN || 
                    this.realtimeRecognition.readyState === WebSocket.CONNECTING) {
                    this.realtimeRecognition.close();
                }
            } catch (err) {
                console.error('❌ 关闭WebSocket连接失败:', err);
            }
            this.realtimeRecognition = null;
        }
        
        this.cleanupAudioResources();
        this.hideVoiceRecognitionArea();
        
        this.streamingSessionActive = false;
        this.isVoiceActive = false;
        this.recognizedText = '';
        this.finalResults = [];
        
        if (this.elements.messageInput) {
            this.elements.messageInput.value = '';
            this.updateCharCount();
        }
        
        this.hasSentCurrentRecognition = false;
    }

    /**
     * 开始录音
     */
    startRecording() {
        if (this.mediaRecorder && this.mediaRecorder.state === 'inactive') {
            this.audioChunks = [];
            this.pcmBuffer = [];
            this.lastSendTime = 0;
            this.mediaRecorder.start();
            this.isMicrophoneActive = true;
            this.updateMicrophoneButton();
            console.log('✅ 录音已启动');
        }
    }

    /**
     * 停止录音
     */
    stopRecording() {
        if (this.mediaRecorder && this.mediaRecorder.state === 'recording') {
            this.mediaRecorder.stop();
            this.isMicrophoneActive = false;
            this.updateMicrophoneButton();
            console.log('停止录音');
        }
    }

    /**
     * ★★★ 核心方法：处理实时语音识别结果 ★★★
     * 
     * 设计原则：只有后端 VAD 发送的 final 结果才会触发发送到 RAG
     * interim 结果只用于实时显示，不触发任何发送操作
     */
    handleRealtimeSpeechResult(data) {
        console.log('🔍 处理语音识别结果:', data.type, '已发送:', this.hasSentCurrentRecognition, 'RAG生成中:', this.isGeneratingResponse);
        
        switch (data.type) {
            case 'ready':
                console.log('✅ 服务器就绪:', data.message);
                break;
                
            case 'partial':
            case 'interim':
                // ========== 中间结果：只更新显示，绝不触发发送 ==========
                if (data.text && data.text.trim()) {
                    // 如果已经发送过或正在生成响应，忽略
                    if (this.hasSentCurrentRecognition || this.isGeneratingResponse) {
                        console.log('⏭️ [interim] 忽略（已发送或正在生成）');
                        return;
                    }
                    
                    this.recognizedText = data.text;
                    this.updateVoiceRecognitionDisplay(this.recognizedText, false);
                    this.elements.messageInput.value = this.recognizedText;
                    this.updateCharCount();
                    this.lastRecognitionTime = Date.now();
                    
                    // 重置UI超时（不触发发送）
                    this.resetRecognitionTimeout();
                }
                break;
                
            case 'final':
                // ========== 最终结果：唯一的发送触发点 ==========
                if (data.text && data.text.trim()) {
                    // 多重防护：防止重复发送
                    if (this.hasSentCurrentRecognition) {
                        console.log('⏭️ [final] 已发送，忽略');
                        return;
                    }
                    
                    if (this.isGeneratingResponse) {
                        console.log('⏭️ [final] 正在生成响应，忽略');
                        return;
                    }
                    
                    const finalText = data.text.trim();
                    console.log('📤 [final] 收到最终结果，立即发送:', finalText);
                    
                    // ★★★ 关键：立即设置标志，防止任何并发触发 ★★★
                    this.hasSentCurrentRecognition = true;
                    
                    // 更新显示
                    this.recognizedText = finalText;
                    this.updateVoiceRecognitionDisplay(this.recognizedText, true);
                    this.elements.messageInput.value = this.recognizedText;
                    this.updateCharCount();
                    
                    // 停止当前音频（如果有）
                    this.stopAudio();
                    
                    // 立即发送到RAG
                    this.sendRecognizedTextToRAG(finalText);
                }
                break;
                
            case 'end':
                console.log('🏁 识别会话结束');
                this.isVoiceActive = false;
                break;
                
            case 'status':
                console.log('📊 状态消息:', data.message);
                if (data.message && data.message.includes('语音识别已结束')) {
                    this.isVoiceActive = false;
                    this.prepareForNextRecording();
                }
                break;
                
            case 'error':
                console.error('❌ 语音识别错误:', data.error);
                this.isVoiceActive = false;
                this.isVoiceMode = false;
                this.hasSentCurrentRecognition = false;
                this.showError('语音识别失败: ' + data.error);
                break;
        }
    }

    /**
     * 重置识别超时（仅用于UI）
     */
    resetRecognitionTimeout() {
        if (this.recognitionTimeout) {
            clearTimeout(this.recognitionTimeout);
        }
        // 5秒无新识别，隐藏识别区域（仅UI操作，不触发发送）
        this.recognitionTimeout = setTimeout(() => {
            console.log('⏱️ [UI超时] 5秒无新识别，隐藏识别区域');
            this.hideVoiceRecognitionArea();
        }, 5000);
    }

    /**
     * 发送识别结果到RAG
     */
    sendRecognizedTextToRAG(text) {
        if (!text || !text.trim()) return;
        
        // 再次检查防止重复
        if (this.isGeneratingResponse) {
            console.log('⏭️ [发送RAG] 正在生成响应，忽略');
            return;
        }
        
        console.log('📤 [发送RAG] 发送:', text);
        
        // 生成请求ID
        const requestId = Date.now();
        this.currentResponseRequestId = requestId;
        this.isGeneratingResponse = true;
        
        // 标记为语音模式，启用自动TTS
        this.isVoiceMode = true;
        console.log('🎤 [语音模式] 已启用');
        
        // 添加用户消息
        this.addMessage('user', text, false, true);
        
        // 发送到服务器
        this.sendToServer('send_message', {
            message: text,
            sessionId: this.sessionId,
            requestId: requestId
        });
        
        // 清理UI
        this.elements.messageInput.value = '';
        this.updateCharCount();
        this.hideVoiceRecognitionArea();
        
        this.recognizedText = '';
        this.finalResults = [];
    }

    /**
     * 准备下次录音
     */
    prepareForNextRecording() {
        console.log('🔄 准备下次录音...');
        
        if (!this.realtimeRecognition || this.realtimeRecognition.readyState !== WebSocket.OPEN) {
            console.log('⚠️ WebSocket已关闭，重新连接...');
            this.initializeRealtimeSpeechRecognition().catch(err => {
                console.error('❌ 重连失败:', err);
            });
        }
        
        this.recognizedText = '';
        this.hasSentCurrentRecognition = false;
    }

    // ========================================================================
    // 第二部分：语音合成(TTS)模块
    // ========================================================================

    /**
     * 朗读文本
     */
    speakText(text, ttsRequestId = null) {
        if (ttsRequestId && this.currentTTSRequestId && ttsRequestId !== this.currentTTSRequestId) {
            console.log('⏭️ [忽略TTS] 收到旧请求的TTS');
            return;
        }
        
        if (this.shouldIgnoreResponse) {
            console.log('⏭️ [忽略] 用户已停止');
            return;
        }
        
        this.stopAudio();
        this.speakWithEdgeTTS(text);
    }

    /**
     * 使用Edge-TTS进行语音合成（非流式模式）
     */
    async speakWithEdgeTTS(text) {
        try {
            this.stopAudioPlaybackOnly(); 
            
            if (this.ttsWebSocket) {
                const oldSocket = this.ttsWebSocket;
                console.log('🔄 [非流式TTS] 检测到旧连接，强制关闭...');
                oldSocket.onopen = null;
                oldSocket.onmessage = null;
                oldSocket.onerror = null;
                oldSocket.onclose = null;
                if (oldSocket.readyState === WebSocket.OPEN || oldSocket.readyState === WebSocket.CONNECTING) {
                    oldSocket.close();
                }
                this.ttsWebSocket = null;
            }

            this.showAudioControls();
            this.audioQueue = [];
            this.isPlayingQueue = false;
            this.isQueueClosing = false;
            this.hasStreamedTTS = false;
            
            const ttsWebSocket = new WebSocket('ws://localhost:8000/ws/tts');
            this.ttsWebSocket = ttsWebSocket;
            
            ttsWebSocket.onopen = () => {
                console.log('✅ [非流式TTS] WebSocket连接已建立');
                ttsWebSocket.send(JSON.stringify({
                    text: text,
                    stream: true
                }));
            };

            ttsWebSocket.onmessage = (event) => {
                if (this.shouldIgnoreResponse) {
                    console.log('⏭️ [忽略] 用户已停止，丢弃TTS音频');
                    return;
                }
                
                const data = JSON.parse(event.data);
                
                if (data.type === 'audio_chunk') {
                    if (data.audio) {
                        this.hasStreamedTTS = true;
                        this.enqueueAudioChunk(data.audio);
                    }
                } else if (data.type === 'audio') {
                    if (this.hasStreamedTTS) {
                        console.log('🎵 [TTS] 已使用流式音频，忽略完整音频');
                        return;
                    }
                    this.playAudioChunk(data.audio);
                } else if (data.type === 'end') {
                    console.log('🎵 [TTS] 合成结束');
                    if (this.hasStreamedTTS) {
                        this.isQueueClosing = true;
                        if (ttsWebSocket.readyState === WebSocket.OPEN) {
                            ttsWebSocket.close();
                        }
                        if (!this.isPlayingQueue && (!this.audioQueue || this.audioQueue.length === 0)) {
                            this.isQueueClosing = false;
                            this.hasStreamedTTS = false;
                            this.hideAudioControls();
                        }
                    } else {
                        ttsWebSocket.close();
                        this.hideAudioControls();
                    }
                } else if (data.type === 'error') {
                    console.error('❌ [TTS] 错误:', data.error);
                    this.hideAudioControls();
                    ttsWebSocket.close();
                }
            };

            ttsWebSocket.onerror = (error) => {
                console.error('[非流式TTS] WebSocket错误:', error);
                this.hideAudioControls();
            };

            ttsWebSocket.onclose = (event) => {
                console.log('🔌[非流式TTS] WebSocket连接已关闭');
                if (this.ttsWebSocket === ttsWebSocket) {
                    this.ttsWebSocket = null;
                }
            };

        } catch (error) {
            console.error('❌ [非流式TTS] 语音合成失败:', error);
            this.hideAudioControls();
            this.showError('语音合成失败');
        }
    }

    /**
     * 只停止音频播放，不关闭TTS连接
     */
    stopAudioPlaybackOnly() {
        if (this.currentAudio) {
            this.currentAudio.pause();
            this.currentAudio.currentTime = 0;
            this.currentAudio = null;
        }
        
        if (this.audioQueue) {
            this.audioQueue.forEach(audio => {
                audio.pause();
                audio.currentTime = 0;
            });
            this.audioQueue = [];
            this.isPlayingQueue = false;
        }
        
        this.hasStreamedTTS = false;
        this.isQueueClosing = false;
    }

    /**
     * 取消当前TTS任务
     */
    cancelCurrentTTS() {
        this.shouldIgnoreResponse = true;
        
        if (this.isStreamingTTSActive) {
            this.cancelStreamingTTS();
        }
        
        this.stopAudio();
        
        if (this.ttsWebSocket) {
            try {
                if (this.ttsWebSocket.readyState === WebSocket.OPEN || 
                    this.ttsWebSocket.readyState === WebSocket.CONNECTING) {
                    this.ttsWebSocket.close();
                }
            } catch (e) {}
            this.ttsWebSocket = null;
        }
        
        this.currentTTSRequestId = Date.now();
    }

    /**
     * 取消流式TTS
     */
    cancelStreamingTTS() {
        console.log('🛑 [流式TTS] 取消');
        this.streamingTTSBuffer = '';
        this.streamingTTSSentenceQueue = [];
        this.isStreamingTTSActive = false;
        this.isProcessingTTSSentence = false;
        this.streamingTTSRequestId = null;
        
        if (this.ttsWebSocket) {
            try { this.ttsWebSocket.close(); } catch (e) {}
            this.ttsWebSocket = null;
        }
        
        this.stopAudio();
    }

    // ========================================================================
    // 第三部分：音频播放模块
    // ========================================================================

    /**
     * 播放完整音频
     */
    playAudioChunk(audioData) {
        if (this.shouldIgnoreResponse) return;
        
        try {
            if (!audioData || audioData.length === 0) {
                console.error('❌ 音频数据为空');
                return;
            }
            
            if (this.currentAudio) {
                try {
                    if (!this.currentAudio.paused) {
                        this.currentAudio.pause();
                    }
                    this.currentAudio.currentTime = 0;
                    this.currentAudio = null;
                } catch (e) {}
            }
            
            const audioUrl = 'data:audio/mp3;base64,' + audioData;
            const audio = new Audio(audioUrl);
            audio.volume = 1.0;
            
            audio.onended = () => {
                console.log('🎵 音频播放完成');
                this.currentAudio = null;
            };
            
            audio.onerror = (e) => {
                console.error('❌ 音频播放错误:', e);
                this.currentAudio = null;
            };
            
            this.currentAudio = audio;
            
            audio.play().then(() => {
                console.log('✅ 音频播放成功');
            }).catch(error => {
                console.error('❌ 音频播放失败:', error);
                this.currentAudio = null;
            });
            
        } catch (error) {
            console.error('❌ 音频处理错误:', error);
            this.currentAudio = null;
        }
    }

    /**
     * 音频入队（用于流式播放）
     */
    enqueueAudioChunk(audioData) {
        if (!audioData || this.shouldIgnoreResponse) return;
        
        try {
            const audioUrl = 'data:audio/mp3;base64,' + audioData;
            const audio = new Audio(audioUrl);
            audio.volume = 1.0;
            
            this.audioQueue.push(audio);
            console.log('🎵 音频入队，队列长度:', this.audioQueue.length);
            
            if (!this.isPlayingQueue) {
                this.playAudioQueue();
            }
        } catch (error) {
            console.error('❌ 无法处理音频:', error);
        }
    }

    /**
     * 播放音频队列
     */
    playAudioQueue() {
        if (this.shouldIgnoreResponse) {
            this.stopAudio();
            return;
        }
        
        if (!this.audioQueue || this.audioQueue.length === 0) {
            console.log('🎵 队列为空');
            this.isPlayingQueue = false;
            if (this.isQueueClosing) {
                this.isQueueClosing = false;
                this.hasStreamedTTS = false;
                this.hideAudioControls();
            }
            return;
        }
        
        this.isPlayingQueue = true;
        const audio = this.audioQueue.shift();
        console.log('🎵 播放队列音频，剩余:', this.audioQueue.length);
        
        audio.play().then(() => {
            console.log('✅ 音频播放成功');
        }).catch(error => {
            console.error('❌ 音频播放失败:', error);
            this.isPlayingQueue = false;
            this.playAudioQueue();
        });
        
        audio.onended = () => {
            console.log('🎵 当前音频完成');
            this.isPlayingQueue = false;
            this.playAudioQueue();
        };
        
        this.currentAudio = audio;
    }

    /**
     * 暂停/继续音频播放
     */
    pauseAudio() {
        if (this.currentAudio) {
            if (this.currentAudio.paused) {
                this.currentAudio.play();
                this.elements.pauseAudio.innerHTML = '<i class="fas fa-pause"></i>';
            } else {
                this.currentAudio.pause();
                this.elements.pauseAudio.innerHTML = '<i class="fas fa-play"></i>';
            }
        }
    }

    /**
     * 停止音频播放
     */
    stopAudio() {
        if (this.currentAudio) {
            this.currentAudio.pause();
            this.currentAudio.currentTime = 0;
            this.currentAudio = null;
        }
        
        if (this.audioQueue) {
            this.audioQueue.forEach(audio => {
                audio.pause();
                audio.currentTime = 0;
            });
            this.audioQueue = [];
            this.isPlayingQueue = false;
        }
        
        if (this.ttsWebSocket) {
            try { this.ttsWebSocket.close(); } catch (e) {}
            this.ttsWebSocket = null;
        }
        
        this.hasStreamedTTS = false;
        this.isQueueClosing = false;
        this.hideAudioControls();
    }

    /**
     * 停止生成（用户点击停止按钮）
     */
    stopGeneration() {
        console.log('🛑 [停止] 用户点击停止');
        
        this.shouldIgnoreResponse = true;
        this.stopAudio();
        
        if (this.ttsWebSocket) {
            try {
                if (this.ttsWebSocket.readyState === WebSocket.OPEN || 
                    this.ttsWebSocket.readyState === WebSocket.CONNECTING) {
                    this.ttsWebSocket.close();
                }
            } catch (e) {}
            this.ttsWebSocket = null;
        }
        
        this.cleanupStreamingMessage();
        this.hideTypingIndicator();
        this.isGeneratingResponse = false;
        this.hasSentCurrentRecognition = false;
        
        console.log('✅ [停止] 操作完成');
    }

    // ========================================================================
    // 第四部分：消息显示模块
    // ========================================================================
    
    /**
     * 发送消息到服务器
     */
    sendToServer(type, data) {
        if (this.socket && this.socket.readyState === WebSocket.OPEN) {
            this.socket.send(JSON.stringify({
                type: type,
                ...data
            }));
        }
    }

    /**
     * 发送消息（文本输入）
     */
    sendMessage() {
        const message = this.elements.messageInput.value.trim();
        if (!message || !this.isConnected) return;

        const isVoiceInput = this.recognizedText && 
                            (message === this.recognizedText.trim() || 
                             message.includes(this.recognizedText.trim()) ||
                             this.recognizedText.trim().includes(message));
        
        if (isVoiceInput) {
            this.isVoiceMode = true;
            console.log('🎤 检测到语音输入，将自动播放回复');
        } else {
            this.isVoiceMode = false;
        }

        // 生成请求ID
        const requestId = Date.now();
        this.currentResponseRequestId = requestId;

        this.addMessage('user', message, false, isVoiceInput);
        
        this.elements.messageInput.value = '';
        this.recognizedText = '';
        this.updateCharCount();
        this.autoResizeTextarea(this.elements.messageInput);

        this.sendToServer('send_message', {
            message: message,
            sessionId: this.socket.id,
            requestId: requestId
        });

        this.hideWelcomeMessage();
    }

    /**
     * 添加消息到聊天界面
     */
    addMessage(role, content, isStreaming = false, isVoiceMessage = false) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${role}`;
        
        const messageContent = document.createElement('div');
        messageContent.className = 'message-content';
        
        if (role === 'assistant') {
            const header = document.createElement('div');
            header.className = 'message-header';
            header.innerHTML = '<i class="fas fa-robot"></i> 博物馆AI助手';
            messageContent.appendChild(header);
        } else if (role === 'user' && isVoiceMessage) {
            const header = document.createElement('div');
            header.className = 'message-header';
            header.innerHTML = '<i class="fas fa-microphone"></i> 语音输入';
            messageContent.appendChild(header);
        }

        const contentDiv = document.createElement('div');
        contentDiv.className = 'message-text';
        if (isStreaming) {
            contentDiv.innerHTML = '<span class="streaming-cursor">|</span>';
            messageDiv.dataset.streaming = 'true';
            messageDiv.dataset.rawText = '';
        } else {
            contentDiv.innerHTML = this.formatMessageContent(content);
        }
        messageContent.appendChild(contentDiv);

        if (role === 'assistant' && content) {
            const actions = this.createMessageActions(content);
            messageContent.appendChild(actions);
        }

        messageDiv.appendChild(messageContent);
        this.elements.chatMessages.appendChild(messageDiv);
        this.scrollToBottom();
        
        return messageDiv;
    }

    /**
     * 创建消息操作按钮
     */
    createMessageActions(content) {
        const actions = document.createElement('div');
        actions.className = 'message-actions';
        
        const speakBtn = document.createElement('button');
        speakBtn.innerHTML = '<i class="fas fa-volume-up"></i> 朗读';
        speakBtn.addEventListener('click', () => {
            this.speakText(content);
        });
        
        const copyBtn = document.createElement('button');
        copyBtn.innerHTML = '<i class="fas fa-copy"></i> 复制';
        copyBtn.addEventListener('click', () => {
            this.copyToClipboard(content);
        });
        
        actions.appendChild(speakBtn);
        actions.appendChild(copyBtn);
        return actions;
    }

    /**
     * 更新最后一条消息（流式更新）
     */
    updateLastMessage(content, isFirst) {
        let lastMessage = this.currentStreamingMessage;
        
        if (!lastMessage || !lastMessage.dataset.streaming) {
            const allStreaming = this.elements.chatMessages.querySelectorAll('.message[data-streaming="true"]');
            lastMessage = allStreaming.length > 0 ? allStreaming[allStreaming.length - 1] : null;
        }
        
        if (lastMessage) {
            const textDiv = lastMessage.querySelector('.message-text');
            const previousText = lastMessage.dataset.rawText || '';
            lastMessage.dataset.rawText = isFirst ? content : (previousText + content);
            textDiv.innerHTML = this.formatMessageContent(lastMessage.dataset.rawText) + '<span class="streaming-cursor">|</span>';
            this.scrollToBottom();
        } else {
            console.warn('⚠️ [updateLastMessage] 找不到流式消息元素');
        }
    }

    /**
     * 完成最后一条消息
     */
    finalizeLastMessage(fullResponse) {
        let lastMessage = this.currentStreamingMessage;
        
        if (!lastMessage || !lastMessage.dataset.streaming) {
            const allStreaming = this.elements.chatMessages.querySelectorAll('.message[data-streaming="true"]');
            lastMessage = allStreaming.length > 0 ? allStreaming[allStreaming.length - 1] : null;
        }
        
        if (lastMessage) {
            const textDiv = lastMessage.querySelector('.message-text');
            textDiv.innerHTML = this.formatMessageContent(fullResponse);
            delete lastMessage.dataset.streaming;
            delete lastMessage.dataset.rawText;
            
            const actions = this.createMessageActions(fullResponse);
            lastMessage.querySelector('.message-content').appendChild(actions);
        }
        
        this.currentStreamingMessage = null;
    }

    /**
     * 清理流式消息
     */
    cleanupStreamingMessage() {
        let streamingMessage = this.currentStreamingMessage;
        
        if (!streamingMessage || !streamingMessage.dataset.streaming) {
            streamingMessage = this.elements.chatMessages.querySelector('.message[data-streaming="true"]');
        }
        
        if (streamingMessage) {
            const textDiv = streamingMessage.querySelector('.message-text');
            const currentText = streamingMessage.dataset.rawText || '';
            if (currentText) {
                textDiv.innerHTML = this.formatMessageContent(currentText) + '<span style="color: #999; font-size: 0.9em;"> (已停止)</span>';
            } else {
                streamingMessage.remove();
            }
            delete streamingMessage.dataset.streaming;
            delete streamingMessage.dataset.rawText;
        }
        
        this.currentStreamingMessage = null;
    }

    // ========================================================================
    // 第五部分：辅助方法
    // ========================================================================

    /**
     * 更新麦克风按钮状态
     */
    updateMicrophoneButton() {
        const micBtn = this.elements.micBtn;
        
        if (this.isMicrophoneActive || this.streamingSessionActive) {
            micBtn.classList.add('recording');
            micBtn.title = '结束语音对话';
            micBtn.textContent = '结束语音对话';
        } else {
            micBtn.classList.remove('recording');
            micBtn.title = '开始语音对话';
            micBtn.textContent = '开始语音对话';
        }
    }

    /**
     * 更新语音识别显示区域
     */
    updateVoiceRecognitionDisplay(text, isFinal) {
        if (text.trim()) {
            this.elements.voiceRecognitionText.textContent = text;
            this.elements.voiceRecognitionArea.style.display = 'block';
            this.elements.voiceRecognitionArea.classList.add('listening');
        }
    }

    /**
     * 隐藏语音识别显示区域
     */
    hideVoiceRecognitionArea() {
        this.elements.voiceRecognitionArea.style.display = 'none';
        this.elements.voiceRecognitionArea.classList.remove('listening');
    }

    /**
     * 清理音频资源
     */
    cleanupAudioResources() {
        console.log('🧹 清理音频资源...');
        
        if (this.processor) {
            try { this.processor.disconnect(); } catch (e) {}
            this.processor = null;
        }
        
        if (this.audioSource) {
            try { this.audioSource.disconnect(); } catch (e) {}
            this.audioSource = null;
        }
        
        if (this.audioContext && this.audioContext.state !== 'closed') {
            this.audioContext.close().catch(e => {});
        }
        this.audioContext = null;
        
        if (this.mediaRecorder && this.mediaRecorder.state !== 'inactive') {
            try { this.mediaRecorder.stop(); } catch (e) {}
        }
        this.mediaRecorder = null;
        
        if (this.audioStream) {
            this.audioStream.getTracks().forEach(track => track.stop());
            this.audioStream = null;
        }
        
        this.pcmBuffer = [];
        this.audioChunks = [];
        this.lastSendTime = 0;
    }

    /**
     * 格式化消息内容
     */
    formatMessageContent(text = '') {
        if (!text) return '';
        const escaped = text
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
        return escaped.replace(/\n/g, '<br>');
    }

    /**
     * 复制到剪贴板
     */
    copyToClipboard(text) {
        navigator.clipboard.writeText(text).then(() => {
            this.showToast('已复制到剪贴板');
        }).catch(() => {
            this.showError('复制失败');
        });
    }

    /**
     * 清空聊天
     */
    clearChat() {
        if (confirm('确定要清空所有对话吗？')) {
            this.elements.chatMessages.innerHTML = '';
            this.chatHistory = [];
            this.showWelcomeMessage();
        }
    }

    /**
     * 显示欢迎消息
     */
    showWelcomeMessage() {
        const welcomeDiv = document.createElement('div');
        welcomeDiv.className = 'welcome-message';
        welcomeDiv.innerHTML = `
            <div class="welcome-content">
                <i class="fas fa-robot"></i>
                <h2>欢迎来到湖北博物馆智能问答系统</h2>
                <p>我是您的专属博物馆导游，可以为您介绍湖北博物馆的历史文化、展品信息、参观指南等。</p>
                <div class="suggested-questions">
                    <h3>您可以问我：</h3>
                    <div class="question-chips">
                        <button class="chip" data-question="湖北博物馆有哪些特色展品？">特色展品介绍</button>
                        <button class="chip" data-question="湖北博物馆的开放时间是什么？">开放时间</button>
                        <button class="chip" data-question="如何预约参观湖北博物馆？">参观预约</button>
                        <button class="chip" data-question="湖北博物馆的历史背景是什么？">历史背景</button>
                    </div>
                </div>
            </div>
        `;
        
        this.elements.chatMessages.appendChild(welcomeDiv);
        welcomeDiv.querySelectorAll('.chip').forEach(chip => {
            chip.addEventListener('click', (e) => {
                const question = e.target.getAttribute('data-question');
                this.elements.messageInput.value = question;
                this.sendMessage();
            });
        });
    }

    /**
     * 隐藏欢迎消息
     */
    hideWelcomeMessage() {
        const welcomeMessage = this.elements.chatMessages.querySelector('.welcome-message');
        if (welcomeMessage) {
            welcomeMessage.remove();
        }
    }

    // ----- UI辅助方法 -----

    showTypingIndicator() {
        this.elements.typingIndicator.style.display = 'flex';
    }

    hideTypingIndicator() {
        this.elements.typingIndicator.style.display = 'none';
    }

    showAudioControls() {
        this.elements.audioControls.style.display = 'flex';
    }

    hideAudioControls() {
        this.elements.audioControls.style.display = 'none';
    }

    updateConnectionStatus(status) {
        const statusElement = this.elements.connectionStatus.querySelector('.status-indicator');
        statusElement.className = `status-indicator ${status}`;
        
        const statusText = {
            'connected': '已连接',
            'disconnected': '连接断开',
            'connecting': '连接中...'
        };
        
        statusElement.querySelector('span').textContent = statusText[status];
    }

    showLoading() {
        this.elements.loadingOverlay.style.display = 'flex';
    }

    hideLoading() {
        this.elements.loadingOverlay.style.display = 'none';
    }

    showError(message) {
        this.elements.errorMessage.textContent = message;
        this.elements.errorModal.style.display = 'flex';
    }

    hideError() {
        this.elements.errorModal.style.display = 'none';
    }

    showToast(message) {
        const toast = document.createElement('div');
        toast.className = 'toast';
        toast.textContent = message;
        toast.style.cssText = `
            position: fixed;
            top: 20px;
            left: 50%;
            transform: translateX(-50%);
            background: #4caf50;
            color: white;
            padding: 1rem 2rem;
            border-radius: 25px;
            z-index: 3000;
            animation: fadeInUp 0.3s ease;
        `;
        
        document.body.appendChild(toast);
        
        setTimeout(() => {
            toast.remove();
        }, 3000);
    }

    autoResizeTextarea(textarea) {
        textarea.style.height = 'auto';
        textarea.style.height = Math.min(textarea.scrollHeight, 120) + 'px';
    }

    updateCharCount() {
        const count = this.elements.messageInput.value.length;
        this.elements.charCount.textContent = `${count}/1000`;
        
        if (count > 800) {
            this.elements.charCount.style.color = '#f44336';
        } else if (count > 600) {
            this.elements.charCount.style.color = '#ff9800';
        } else {
            this.elements.charCount.style.color = '#666';
        }
    }

    scrollToBottom() {
        this.elements.chatMessages.scrollTop = this.elements.chatMessages.scrollHeight;
    }
}

// ============================================================================
// 初始化应用
// ============================================================================
const app = new MuseumChatApp();

window.addEventListener('load', () => {
    if ('speechSynthesis' in window) {
        speechSynthesis.getVoices();
    }
});

document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
        if (speechSynthesis.speaking) {
            speechSynthesis.pause();
        }
    }
});
