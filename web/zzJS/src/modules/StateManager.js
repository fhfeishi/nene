/**
 * web/zzJS/src/modules/StateManager.js
 * 状态管理模块 - 这里的原则是：UI 只是状态的“观察者”
 */
import { APP_STATE } from '../config.js';

export class StateManager {
    constructor() {
        this.currentState = APP_STATE.IDLE;
        this.listeners = []; // 订阅者列表
    }

    /**
     * 获取当前状态
     */
    getState() {
        return this.currentState;
    }

    /**
     * 切换状态
     * @param {string} newState - 新状态
     * @param {object} payload - 伴随数据（比如错误信息、识别到的文本等）
     */
    setState(newState, payload = null) {
        if (this.currentState === newState) return;

        console.log(`[State] ${this.currentState} -> ${newState}`, payload || '');
        
        // 可以在这里添加状态流转的合法性检查（例如：不能从 IDLE 直接跳到 SPEAKING）
        
        this.currentState = newState;
        this._notify(newState, payload);
    }

    /**
     * 订阅状态变化
     * @param {Function} callback 
     */
    subscribe(callback) {
        this.listeners.push(callback);
    }

    _notify(newState, payload) {
        this.listeners.forEach(callback => callback(newState, payload));
    }
}