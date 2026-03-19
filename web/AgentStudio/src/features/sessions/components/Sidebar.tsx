// src/sessions/components/Sidebar.tsx

import React from 'react';
import { motion } from 'framer-motion';
import { Plus, MessageSquare, Settings } from 'lucide-react';

interface SidebarProps {
    isOpen: boolean;
}

export const Sidebar: React.FC<SidebarProps> = ({ isOpen }) => {
    return (
        <aside
            className={`${isOpen ? 'w-66' : 'w-0'} flex-shrink-0 bg-gray-950 text-gray-300 flex flex-col transition-all duration-300 ease-in-out overflow-hidden relative border-r border-gray-800/50`}
        >
            <div className="p-3.5">
                <motion.button
                    className="flex items-center gap-2.5 w-full px-4 py-2.5 bg-blue-600 hover:bg-blue-700 text-white rounded-xl text-sm font-medium transition-colors shadow-blue-500/20 shadow-md"
                    whileTap={{ scale: 0.98 }}
                >
                    <Plus size={18} />
                    <span className="truncate">新建对话</span>
                </motion.button>
            </div>

            <div className="flex-1 overflow-y-auto px-3.5 py-2 space-y-1 scrollbar-thin">
                <div className="text-xs font-semibold text-gray-600 mb-2.5 px-3 mt-4 uppercase tracking-wider">最近会话</div>
                {['架构设计', 'React 调试', '邮件撰写'].map((title, idx) => (
                    <motion.button
                        key={idx}
                        className={`flex items-center gap-3.5 w-full px-3.5 py-2.5 rounded-lg text-sm transition-all ${
                            idx === 0 ? 'bg-gray-800 text-white font-medium' : 'text-gray-400 hover:bg-gray-800/70 hover:text-white'
                        }`}
                        whileHover={{ x: 3 }}
                    >
                        <MessageSquare size={16} className={idx === 0 ? 'text-blue-400' : 'text-gray-600'} />
                        <span className="truncate flex-1 text-left">{title}</span>
                    </motion.button>
                ))}
            </div>

            <div className="p-3 border-t border-gray-800/80">
                <button className="flex items-center gap-3.5 w-full px-4 py-2.5 hover:bg-gray-800 rounded-lg text-sm text-gray-400 hover:text-white transition-colors">
                    <Settings size={18} />
                    <span>系统设置</span>
                </button>
            </div>
        </aside>
    );
};