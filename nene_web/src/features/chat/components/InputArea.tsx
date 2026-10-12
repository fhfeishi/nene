// src/features/chat/components/InputArea.tsx

import React, { useState, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Paperclip, Mic, Send, MicOff } from 'lucide-react';
import { useChatStore } from '../../../store/useChatStore.ts';
import { useWebSpeech } from '../../../hooks/useWebSpeech.ts';

export const InputArea: React.FC = () => {
    const [inputText, setInputText] = useState('');
    const textareaRef = useRef<HTMLTextAreaElement>(null);
    const addMessage = useChatStore((state) => state.addMessage);

    // === 接入语音识别 Hook ===
    const { isListening, startListening, stopListening, isSupported } = useWebSpeech({
        onResult: (text) => {
            setInputText(text); // 实时更新输入框文字
            adjustHeight();
        },
        onError: (err) => {
            alert(`语音识别出错: ${err}`);
        }
    });

    const adjustHeight = () => {
        if (textareaRef.current) {
            textareaRef.current.style.height = 'auto';
            textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 144)}px`;
        }
    };

    const handleSend = () => {
        if (!inputText.trim()) return;
        addMessage({ sessionId: 'default', role: 'user', content: inputText.trim() });
        setInputText('');
        if (textareaRef.current) textareaRef.current.style.height = 'auto';

        // 模拟回复逻辑（略...）
    };

    return (
        <div className="p-5 pb-6 bg-transparent shrink-0 w-full relative">
            {/* 语音录制中的动态提示条 */}
            <AnimatePresence>
                {isListening && (
                    <motion.div
                        initial={{ opacity: 0, y: 10 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: 10 }}
                        className="absolute -top-4 left-1/2 -translate-x-1/2 bg-brand-primary text-white text-[10px] px-3 py-1 rounded-full shadow-lg flex items-center gap-2"
                    >
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-white opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2 w-2 bg-white"></span>
            </span>
                        正在倾听...
                    </motion.div>
                )}
            </AnimatePresence>

            <div className={`w-full max-w-3xl mx-auto relative flex items-end gap-2.5 bg-white border shadow-lg rounded-3xl px-4 py-3.5 transition-all ${
                isListening ? 'border-brand-primary ring-4 ring-brand-primary/10 scale-[1.01]' : 'border-slate-200'
            }`}>
                <button className="p-2.5 text-slate-400 hover:text-gray-700 hover:bg-gray-100 rounded-xl transition-colors shrink-0">
                    <Paperclip size={20} />
                </button>

                <textarea
                    ref={textareaRef}
                    value={inputText}
                    onChange={(e) => { setInputText(e.target.value); adjustHeight(); }}
                    onKeyDown={(e) => e.key === 'Enter' && !e.shiftKey && (e.preventDefault(), handleSend())}
                    rows={1}
                    className="flex-1 bg-transparent outline-none resize-none py-1.5 text-gray-800 placeholder-gray-400 text-base max-h-36 leading-relaxed"
                    placeholder={isListening ? "请说话..." : "问问我任何事情..."}
                />

                {/* 麦克风按钮：点击切换开始/停止 */}
                {isSupported && (
                    <button
                        onClick={isListening ? stopListening : startListening}
                        className={`p-2.5 rounded-xl transition-all shrink-0 ${
                            isListening
                                ? 'bg-brand-primary text-white shadow-inner'
                                : 'text-slate-400 hover:text-brand-primary hover:bg-blue-50'
                        }`}
                    >
                        {isListening ? <MicOff size={20} className="animate-pulse" /> : <Mic size={20} />}
                    </button>
                )}

                <motion.button
                    onClick={handleSend}
                    disabled={!inputText.trim() || isListening}
                    className="p-2.5 bg-brand-primary text-white hover:bg-brand-primary-hover rounded-full transition-colors shrink-0 shadow-md disabled:opacity-30 disabled:grayscale"
                    whileTap={inputText.trim() ? { scale: 0.92 } : {}}
                >
                    <Send size={18} />
                </motion.button>
            </div>
        </div>
    );
};