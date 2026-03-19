// src/hooks/useWebSpeech.ts

import { useState, useEffect, useCallback, useRef } from 'react';

interface UseWebSpeechOptions {
    onResult?: (text: string) => void;
    onError?: (error: string) => void;
}

export const useWebSpeech = ({ onResult, onError }: UseWebSpeechOptions = {}) => {
    const [isListening, setIsListening] = useState(false);
    const recognitionRef = useRef<any>(null);

    useEffect(() => {
        // 兼容性处理：Chrome 使用 webkitSpeechRecognition
        const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;

        if (!SpeechRecognition) {
            console.error('当前浏览器不支持 Web Speech API');
            return;
        }

        const recognition = new SpeechRecognition();

        // 配置
        recognition.continuous = false;    // 这种模式下，说完整的一句会自动停止
        recognition.interimResults = true; // 是否实时显示中间结果
        recognition.lang = 'zh-CN';        // 设置为中文

        recognition.onstart = () => setIsListening(true);

        recognition.onresult = (event: any) => {
            let transcript = '';
            for (let i = event.resultIndex; i < event.results.length; i++) {
                transcript += event.results[i][0].transcript;
            }
            if (onResult) onResult(transcript);
        };

        recognition.onerror = (event: any) => {
            console.error('STT Error:', event.error);
            setIsListening(false);
            if (onError) onError(event.error);
        };

        recognition.onend = () => setIsListening(false);

        recognitionRef.current = recognition;
    }, [onResult, onError]);

    const startListening = useCallback(() => {
        if (recognitionRef.current && !isListening) {
            try {
                recognitionRef.current.start();
            } catch (e) {
                console.error('识别启动失败:', e);
            }
        }
    }, [isListening]);

    const stopListening = useCallback(() => {
        if (recognitionRef.current && isListening) {
            recognitionRef.current.stop();
        }
    }, [isListening]);

    return {
        isListening,
        startListening,
        stopListening,
        isSupported: !!((window as any).SpeechRecognition || (window as any).webkitSpeechRecognition)
    };
};