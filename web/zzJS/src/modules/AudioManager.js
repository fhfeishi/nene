/**
 * web/zzJS/src/modules/AudioManager.js
 * 负责录音流的采集与处理，以及音频队列的播放
 */
import { CONFIG } from '../config.js';

export class AudioManager {
    constructor() {
        // 录音相关
        this.audioContext = null;
        this.processor = null;
        this.inputSource = null;
        this.stream = null;
        this.onAudioChunk = null; // 回调：当有PCM数据时调用

        // 播放相关
        this.audioQueue = [];     // 播放队列
        this.isPlaying = false;
        this.currentAudio = null; // 当前播放的 Audio 对象
    }

    // ================= 录音部分 =================

    /**
     * 初始化并开始录音
     * @param {Function} dataCallback - 接收 Base64 PCM 数据的回调
     */
    async startRecording(dataCallback) {
        try {
            this.onAudioChunk = dataCallback;
            
            // 获取麦克风流
            this.stream = await navigator.mediaDevices.getUserMedia({
                audio: {
                    echoCancellation: true,
                    noiseSuppression: true,
                    sampleRate: CONFIG.AUDIO.SAMPLE_RATE
                }
            });

            this.audioContext = new (window.AudioContext || window.webkitAudioContext)();
            const sourceSampleRate = this.audioContext.sampleRate;
            
            // 创建处理节点
            this.inputSource = this.audioContext.createMediaStreamSource(this.stream);
            this.processor = this.audioContext.createScriptProcessor(CONFIG.AUDIO.BUFFER_SIZE, 1, 1);

            this.processor.onaudioprocess = (e) => this._processAudio(e, sourceSampleRate);

            // 连接节点：Source -> Processor -> Destination (为了保持活跃)
            this.inputSource.connect(this.processor);
            this.processor.connect(this.audioContext.destination);

        } catch (error) {
            console.error('[Audio] 启动录音失败:', error);
            throw error;
        }
    }

    stopRecording() {
        if (this.processor) {
            this.processor.disconnect();
            this.processor = null;
        }
        if (this.inputSource) {
            this.inputSource.disconnect();
            this.inputSource = null;
        }
        if (this.stream) {
            this.stream.getTracks().forEach(track => track.stop());
            this.stream = null;
        }
        if (this.audioContext) {
            this.audioContext.close();
            this.audioContext = null;
        }
    }

    // 私有：处理音频帧并重采样
    _processAudio(event, sourceRate) {
        if (!this.onAudioChunk) return;

        const inputData = event.inputBuffer.getChannelData(0);
        const targetRate = CONFIG.AUDIO.SAMPLE_RATE;
        
        // 简单重采样逻辑 (Linear Interpolation)
        // 如果浏览器原生支持设置 sampleRate，这一步可以简化，但为了兼容性保留
        let processedData = inputData;
        if (sourceRate !== targetRate) {
            const ratio = sourceRate / targetRate;
            const newLength = Math.round(inputData.length / ratio);
            processedData = new Float32Array(newLength);
            for (let i = 0; i < newLength; i++) {
                processedData[i] = inputData[Math.floor(i * ratio)];
            }
        }

        // 转 16-bit PCM
        const pcm16 = new Int16Array(processedData.length);
        for (let i = 0; i < processedData.length; i++) {
            const s = Math.max(-1, Math.min(1, processedData[i]));
            pcm16[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
        }

        // 转 Base64 发送
        // 注意：实际工程中建议直接发二进制 Blob，这里为了兼容旧后端保持 Base64
        const binary = String.fromCharCode(...new Uint8Array(pcm16.buffer));
        this.onAudioChunk(btoa(binary));
    }

    // ================= 播放部分 =================

    /**
     * 将 Base64 音频块加入播放队列
     */
    enqueueAudio(base64Data) {
        if (!base64Data) return;
        const audioUrl = 'data:audio/mp3;base64,' + base64Data;
        const audio = new Audio(audioUrl);
        this.audioQueue.push(audio);
        
        if (!this.isPlaying) {
            this._playNext();
        }
    }

    _playNext() {
        if (this.audioQueue.length === 0) {
            this.isPlaying = false;
            return;
        }

        this.isPlaying = true;
        this.currentAudio = this.audioQueue.shift();
        
        this.currentAudio.onended = () => {
            this.currentAudio = null;
            this._playNext();
        };

        this.currentAudio.onerror = (e) => {
            console.error('[Audio] 播放错误', e);
            this.currentAudio = null;
            this._playNext();
        };

        this.currentAudio.play().catch(e => console.error('播放被阻止', e));
    }

    /**
     * 停止播放并清空队列（打断机制的关键）
     */
    stopPlayback() {
        // 1. 停止当前
        if (this.currentAudio) {
            this.currentAudio.pause();
            this.currentAudio.currentTime = 0;
            this.currentAudio = null;
        }
        // 2. 清空队列
        this.audioQueue = [];
        this.isPlaying = false;
    }
}