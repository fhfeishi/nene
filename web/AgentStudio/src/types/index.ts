// src/types/index.ts

// ==========================================
// 1. 智能体引擎 (Agent) 相关实体
// ==========================================
export interface Agent {
  id: string;
  name: string;
  description?: string;          // 一句话简介
  avatar?: string;               // 头像（Emoji 或 URL）
  systemPrompt: string;          // 核心人设与指令
  temperature: number;           // 模型发散度 (0.0 - 2.0)
  knowledgeBaseIds: string[];    // 【预留】绑定的知识库文档 ID 列表 (用于 RAG)
  toolIds?: string[];            // 【预留】绑定的插件/工具 ID 列表 (如联网、计算器)
  createdAt: number;             // 时间戳
  updatedAt: number;
}

// ==========================================
// 2. 会话与工作区 (Session & Workspace) 相关实体
// ==========================================
export interface SessionGroup {
  id: string;
  name: string;                  // 文件夹名称（如“项目A”、“旅行计划”）
  createdAt: number;
}

export interface Session {
  id: string;
  agentId: string;               // 核心关联：这个会话是在和哪个 Agent 聊天
  groupId?: string;              // 归属的文件夹 ID（可选，没有则在根目录）
  title: string;                 // 会话标题（由首轮对话自动生成）
  createdAt: number;
  updatedAt: number;
}

// ==========================================
// 3. 消息与交互 (Message & RAG) 相关实体
// ==========================================
export type Role = 'user' | 'assistant' | 'system';

export interface Citation {
  id: string;
  documentId: string;
  documentName: string;          // 来源文档名称 (如 "2026财报.pdf")
  snippet: string;               // 具体的文本切片内容
  score?: number;                // 检索相似度分数
}

export interface Message {
  id: string;
  sessionId: string;
  role: Role;
  content: string;
  parentId?: string | null;      // 【核心】用于消息分支编辑。指向上一条消息的 ID，null 表示这是会话的第一条消息
  citations?: Citation[];        // 【预留】如果回答用到了 RAG，这里存放引用的来源数组
  isError?: boolean;             // 标记是否为系统报错消息（如网络断开）
  createdAt: number;
}

// ==========================================
// 4. 知识库资产 (Knowledge Base) 相关实体预留
// ==========================================
export type DocumentStatus = 'uploading' | 'parsing' | 'embedded' | 'error';

export interface KnowledgeDocument {
  id: string;
  name: string;
  size: number;                  // 文件大小 (bytes)
  status: DocumentStatus;        // 文档处理状态（展示进度条用）
  errorMessage?: string;
  createdAt: number;
}