// src/store/useChatStore.ts
import { create } from 'zustand';
import type { Message } from '../types';

interface ChatState {
  messages: Message[];         // 全局消息池（扁平化存储所有会话的消息）
  isGenerating: boolean;       // 核心 UI 状态：AI 是否正在回复中（用于禁用输入框）
}

interface ChatActions {
  // 核心操作：新增消息
  addMessage: (message: Omit<Message, 'id' | 'createdAt'>) => string;
  // 核心操作：更新消息（常用于流式输出时动态拼接内容，或追加 RAG 的 citations）
  updateMessage: (id: string, updates: Partial<Message>) => void;
  // 核心操作：删除消息（注意：如果是分支树，理想状态下还要级联删除它的子节点）
  deleteMessage: (id: string) => void;
  // UI 交互：设置生成状态
  setGenerating: (isGenerating: boolean) => void;
  // 派生查询：获取指定会话下的所有消息流
  getMessagesBySession: (sessionId: string) => Message[];
}

export const useChatStore = create<ChatState & ChatActions>((set, get) => ({
  // --- 状态 ---
  messages: [],
  isGenerating: false,

  // --- 动作 ---
  addMessage: (msgData) => {
    // 使用浏览器原生的 crypto.randomUUID() 生成唯一 ID，完全脱离后端依赖
    const newId = crypto.randomUUID();
    const newMessage: Message = {
      ...msgData,
      id: newId,
      createdAt: Date.now(),
    };

    set((state) => ({
      messages: [...state.messages, newMessage],
    }));

    // 返回生成的 ID，方便在流式接口调用时，拿到这个 ID 去执行 updateMessage 拼接字符串
    return newId;
  },

  updateMessage: (id, updates) => {
    set((state) => ({
      // React 状态不可变原则：map 遍历并克隆修改目标对象
      messages: state.messages.map((msg) =>
        msg.id === id ? { ...msg, ...updates } : msg
      ),
    }));
  },

  deleteMessage: (id) => {
    set((state) => ({
      messages: state.messages.filter((msg) => msg.id !== id),
    }));
  },

  setGenerating: (isGenerating) => {
    set({ isGenerating });
  },

  getMessagesBySession: (sessionId) => {
    // 过滤出当前会话的消息，并按时间戳排序，确保渲染顺序绝对正确
    const sessionMessages = get().messages.filter(
      (msg) => msg.sessionId === sessionId
    );
    return sessionMessages.sort((a, b) => a.createdAt - b.createdAt);
  },
}));