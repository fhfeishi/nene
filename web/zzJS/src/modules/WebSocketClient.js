/**
 * web/zzJS/src/modules/WebSocketClient.js
 * 通用 WebSocket 客户端，支持自动重连和事件分发
 */
export class WebSocketClient {
    constructor(url, name = 'Client') {
        this.url = url;
        this.name = name;
        this.socket = null;
        this.handlers = {}; // 消息处理器 map: { 'message_type': callback }
        this.isConnected = false;
        this.reconnectTimer = null;
    }

    /**
     * 注册消息处理器
     */
    on(type, handler) {
        this.handlers[type] = handler;
    }

    connect() {
        if (this.socket && (this.socket.readyState === WebSocket.OPEN || this.socket.readyState === WebSocket.CONNECTING)) {
            return;
        }

        console.log(`[${this.name}] 连接中... ${this.url}`);
        this.socket = new WebSocket(this.url);

        this.socket.onopen = () => {
            console.log(`[${this.name}] ✅ 连接成功`);
            this.isConnected = true;
            if (this.handlers['open']) this.handlers['open']();
        };

        this.socket.onclose = (event) => {
            console.warn(`[${this.name}] ❌ 连接断开`);
            this.isConnected = false;
            this._handleReconnect();
            if (this.handlers['close']) this.handlers['close'](event);
        };

        this.socket.onerror = (error) => {
            console.error(`[${this.name}] ⚠️ 连接错误`, error);
            if (this.handlers['error']) this.handlers['error'](error);
        };

        this.socket.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                const type = data.type;
                
                // 路由分发
                if (this.handlers[type]) {
                    this.handlers[type](data);
                } else {
                    console.log(`[${this.name}] 未处理的消息类型: ${type}`);
                }
            } catch (e) {
                console.error(`[${this.name}] 解析消息失败`, event.data);
            }
        };
    }

    send(data) {
        if (this.isConnected && this.socket.readyState === WebSocket.OPEN) {
            this.socket.send(JSON.stringify(data));
        } else {
            console.warn(`[${this.name}] 无法发送，未连接`);
        }
    }

    disconnect() {
        if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
        if (this.socket) {
            this.socket.close();
            this.socket = null;
        }
        this.isConnected = false;
    }

    _handleReconnect() {
        // 简单的重连逻辑，实际工程可以使用指数退避算法
        if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
        this.reconnectTimer = setTimeout(() => {
            console.log(`[${this.name}] 尝试重连...`);
            this.connect();
        }, 3000);
    }
}