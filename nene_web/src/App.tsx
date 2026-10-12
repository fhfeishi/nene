// src/App.tsx
import React, { useState, useRef, useEffect } from 'react';
import { Bot } from 'lucide-react';
import { motion } from 'framer-motion';
import { useChatStore } from './store/useChatStore';

// 引入拆分后的组件
import { Sidebar } from './features/sessions/components/Sidebar';
import { ChatHeader } from './features/chat/components/ChatHeader';
import { MessageBubble } from './features/chat/components/MessageBubble.tsx';
import { InputArea } from './features/chat/components/InputArea.tsx';
import { VoiceCallModal } from './features/voiceCall/components/VoiceCallModal';

export default function App() {
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const messages = useChatStore((state) => state.messages);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  return (
      <div className="flex h-screen w-full bg-gray-100/50 text-gray-800 overflow-hidden font-sans">
        <Sidebar isOpen={isSidebarOpen} />

        <main className="flex-1 flex flex-col h-full relative min-w-0 bg-gray-100/50">
          <ChatHeader onMenuClick={() => setIsSidebarOpen(!isSidebarOpen)} />

          <div className="flex-1 overflow-y-auto p-4 md:p-10 space-y-7 scrollbar-thin">
            {messages.length === 0 ? (
                <motion.div
                    className="w-full flex flex-col items-center justify-center text-gray-400 mt-28"
                    initial={{ opacity: 0 }} animate={{ opacity: 1 }}
                >
                  <div className="w-20 h-20 bg-blue-50 rounded-3xl flex items-center justify-center mb-6 border border-blue-100 shadow-xl">
                    <Bot size={40} className="text-blue-500" />
                  </div>
                  <p className="text-gray-600 font-medium text-base">你好！我是你的智能体助手</p>
                </motion.div>
            ) : (
                messages.map((msg) => <MessageBubble key={msg.id} message={msg} />)
            )}
            <div ref={messagesEndRef} />
          </div>

          <InputArea />
        </main>
          <VoiceCallModal />
      </div>
  );
}