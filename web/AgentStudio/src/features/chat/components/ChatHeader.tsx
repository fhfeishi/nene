// src/features/chat/components/ChatHeader.tsx

import React from 'react';
import { motion } from 'framer-motion';
import { Menu, Bot, Phone } from 'lucide-react';
import { ThemeToggle } from '../../common/ThemeToggle'; // 确保路径正确
import { useAppStore } from '../../../store/useAppStore'; // 引入 Store

interface ChatHeaderProps {
    onMenuClick: () => void;
}

export const ChatHeader: React.FC<ChatHeaderProps> = ({ onMenuClick }) => {
    // 获取 setVoiceCallActive 方法
    const setVoiceCallActive = useAppStore((state) => state.setVoiceCallActive);


    return (
        <header className="h-16 bg-brand-surface/90 backdrop-blur-md border-b border-brand-border flex items-center justify-between px-5 z-10 sticky top-0 transition-colors duration-300">

            {/* 左侧：菜单开关与标题 */}
            <div className="flex items-center gap-3.5">
                <button
                    onClick={onMenuClick}
                    className="p-2 -ml-2 text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-lg transition-colors"
                >
                    <Menu size={20} />
                </button>
                <div className="flex items-center gap-2.5">
                    <div className="w-9 h-9 bg-blue-50 dark:bg-blue-900/30 flex items-center justify-center rounded-xl border border-blue-100 dark:border-blue-800 shadow-inner">
                        <Bot size={22} className="text-brand-primary" />
                    </div>
                    <h1 className="font-bold text-brand-text text-lg tracking-tight">Agent Studio</h1>
                </div>
            </div>

            {/* 右侧：功能按钮组 */}
            <div className="flex items-center gap-3">
                {/* 主题切换开关 */}
                <ThemeToggle />

                {/* 语音通话模式入口 */}
                <motion.button
                    onClick={() => setVoiceCallActive(true)} // 点击开启
                    className="flex items-center gap-2 px-4 py-1.5 bg-emerald-50 dark:bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 rounded-full text-sm font-medium border border-emerald-200 dark:border-emerald-500/20 shadow-sm shadow-emerald-100/50"
                    whileTap={{ scale: 0.95 }}
                    whileHover={{ y: -1 }}
                >
                    <Phone size={16} />
                    <span className="hidden sm:inline">语音通话</span>
                </motion.button>
            </div>

        </header>
    );
};