/**
 * web/zzJS/src/modules/UIManager.js
 * 负责界面渲染，包含流式消息显示
 */
export class UIManager {
    constructor() {
        // DOM 元素缓存
        this.els = {
            chatContainer: document.getElementById('chatMessages'),
            input: document.getElementById('messageInput'),
            sendBtn: document.getElementById('sendBtn'),
            micBtn: document.getElementById('micBtn'),
            stopBtn: document.getElementById('stopBtn'),
            status: document.getElementById('connectionStatus'),
            typing: document.getElementById('typingIndicator'),
            voicePanel: document.getElementById('voiceRecognitionArea'),
            voiceText: document.getElementById('voiceRecognitionText')
        };

        this.currentStreamingMessage = null; // 当前正在流式输出的消息 DOM
    }

    // 更新连接状态 UI
    updateConnectionStatus(isConnected) {
        const text = isConnected ? '已连接' : '断开';
        const color = isConnected ? 'green' : 'red';
        this.els.status.innerHTML = `<span style="color:${color}">●</span> ${text}`;
    }

    // 更新麦克风按钮样式
    setMicActive(isActive) {
        if (isActive) {
            this.els.micBtn.classList.add('recording');
            this.els.micBtn.textContent = '停止说话';
            this.els.voicePanel.style.display = 'block';
        } else {
            this.els.micBtn.classList.remove('recording');
            this.els.micBtn.textContent = '点击说话';
            this.els.voicePanel.style.display = 'none';
        }
    }

    // 更新实时语音识别文本
    updateVoiceText(text) {
        this.els.voiceText.textContent = text || '正在听...';
    }

    // 添加用户消息
    addUserMessage(text) {
        this._appendMessage('user', text);
    }

    // 开始一条新的 AI 消息（流式）
    startAssistantMessage() {
        const msgDiv = document.createElement('div');
        msgDiv.className = 'message assistant';
        msgDiv.innerHTML = `
            <div class="content">
                <span class="text"></span><span class="cursor">|</span>
            </div>`;
        this.els.chatContainer.appendChild(msgDiv);
        this._scrollToBottom();
        this.currentStreamingMessage = msgDiv;
        return msgDiv;
    }

    // 追加 AI 消息内容
    appendAssistantChunk(chunk) {
        if (this.currentStreamingMessage) {
            const textSpan = this.currentStreamingMessage.querySelector('.text');
            textSpan.innerHTML += this._escapeHtml(chunk); // 注意：这里简单追加，实际可以用之前的 accumulatedText 逻辑
            this._scrollToBottom();
        }
    }

    // 结束 AI 消息
    finishAssistantMessage() {
        if (this.currentStreamingMessage) {
            const cursor = this.currentStreamingMessage.querySelector('.cursor');
            if (cursor) cursor.remove();
            this.currentStreamingMessage = null;
        }
    }

    // 内部方法
    _appendMessage(role, text) {
        const div = document.createElement('div');
        div.className = `message ${role}`;
        div.innerHTML = `<div class="content">${this._escapeHtml(text)}</div>`;
        this.els.chatContainer.appendChild(div);
        this._scrollToBottom();
    }

    _scrollToBottom() {
        this.els.chatContainer.scrollTop = this.els.chatContainer.scrollHeight;
    }

    _escapeHtml(text) {
        if (!text) return '';
        return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/\n/g, "<br>");
    }
    
    bindEvents(handlers) {
        this.els.sendBtn.onclick = () => {
            const text = this.els.input.value.trim();
            if (text) {
                handlers.onSend(text);
                this.els.input.value = '';
            }
        };
        
        this.els.micBtn.onclick = handlers.onMicToggle;
        this.els.stopBtn.onclick = handlers.onStop;
    }
}