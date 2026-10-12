// src/features/chat/components/MessageBubble.tsx

import React, { useState, useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Bot, User, Clipboard, Check, Volume2 } from 'lucide-react';
import type { Message } from '../../../types';

interface MessageBubbleProps {
    message: Message;
}

// 1. 声音脉动动效组件 (类似音乐播放器的跳动条)
const AudioPulse = () => (
    <div className="flex items-center gap-0.5 h-3 px-1">
        {[0, 1, 2].map((i) => (
            <motion.div
                key={i}
                className="w-0.75 bg-brand-primary rounded-full"
                animate={{
                    height: ["20%", "100%", "20%"],
                }}
                transition={{
                    repeat: Infinity,
                    duration: 0.6,
                    delay: i * 0.2,
                    ease: "easeInOut"
                }}
            />
        ))}
    </div>
);

export const MessageBubble: React.FC<MessageBubbleProps> = ({ message }) => {
    const isUser = message.role === 'user';
    const [copied, setCopied] = useState(false);
    const [isSpeaking, setIsSpeaking] = useState(false);
    const [isHovered, setIsHovered] = useState(false);

    const synthRef = useRef<SpeechSynthesis>(window.speechSynthesis);
    const utteranceRef = useRef<SpeechSynthesisUtterance | null>(null);

    useEffect(() => {
        return () => synthRef.current.cancel();
    }, []);

    const handleCopy = async () => {
        await navigator.clipboard.writeText(message.content);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
    };

    const handleSpeak = () => {
        if (isSpeaking) {
            synthRef.current.cancel();
            setIsSpeaking(false);
            return;
        }

        synthRef.current.cancel();
        utteranceRef.current = new SpeechSynthesisUtterance(message.content);
        utteranceRef.current.lang = 'zh-CN';

        utteranceRef.current.onstart = () => setIsSpeaking(true);
        utteranceRef.current.onend = () => setIsSpeaking(false);
        utteranceRef.current.onerror = () => setIsSpeaking(false);

        synthRef.current.speak(utteranceRef.current);
    };

    return (
        <motion.div
            className="w-full group/bubble"
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            onMouseEnter={() => setIsHovered(true)}
            onMouseLeave={() => setIsHovered(false)}
        >
            <div className={`flex gap-4 w-full max-w-3xl mx-auto ${isUser ? 'flex-row-reverse' : ''}`}>

                {/* 头像 */}
                <div className={`w-9 h-9 rounded-xl flex items-center justify-center flex-shrink-0 mt-1 border shadow-sm transition-all ${
                    isUser ? 'bg-white border-slate-200' : 'bg-blue-50 border-blue-100'
                }`}>
                    {isUser ? <User size={18} className="text-slate-500" /> : <Bot size={20} className="text-brand-primary" />}
                </div>

                {/* 气泡内容 */}
                <div className={`flex flex-col gap-2 flex-1 ${isUser ? 'items-end' : ''}`}>
                    <div className={`px-5 py-3 text-sm md:text-base leading-relaxed shadow-sm transition-all ${
                        isUser
                            ? 'bg-gradient-to-br from-brand-ai-start to-brand-primary text-white rounded-2xl rounded-tr-none'
                            : 'bg-white border border-slate-200/60 text-slate-800 rounded-2xl rounded-tl-none'
                    }`}>
                        {message.content}
                    </div>

                    {/* 交互工具栏 */}
                    {!isUser && (
                        <div className="flex items-center gap-1 h-8">
                            <AnimatePresence>
                                {(isHovered || isSpeaking) && (
                                    <motion.div
                                        initial={{ opacity: 0, x: -10 }}
                                        animate={{ opacity: 1, x: 0 }}
                                        exit={{ opacity: 0, x: -10 }}
                                        className="flex items-center bg-white/50 backdrop-blur-sm border border-slate-100 rounded-full px-1 py-0.5 shadow-sm"
                                    >
                                        {/* 朗读按钮：动态切换动效与颜色 */}
                                        <button
                                            onClick={handleSpeak}
                                            className={`flex items-center gap-1 px-2 py-1 rounded-full transition-all ${
                                                isSpeaking
                                                    ? 'text-brand-primary bg-blue-50'
                                                    : 'text-slate-400 hover:text-brand-primary hover:bg-slate-50'
                                            }`}
                                        >
                                            <Volume2 size={16} className={isSpeaking ? 'animate-pulse' : ''} />
                                            {isSpeaking && <AudioPulse />}
                                        </button>

                                        <div className="w-[1px] h-3 bg-slate-200 mx-1" />

                                        {/* 复制按钮 */}
                                        <button
                                            onClick={handleCopy}
                                            className="p-1.5 text-slate-400 hover:text-brand-primary hover:bg-slate-50 rounded-full transition-all"
                                        >
                                            {copied ? <Check size={15} className="text-emerald-500" /> : <Clipboard size={15} />}
                                        </button>
                                    </motion.div>
                                )}
                            </AnimatePresence>
                        </div>
                    )}
                </div>
            </div>
        </motion.div>
    );
};