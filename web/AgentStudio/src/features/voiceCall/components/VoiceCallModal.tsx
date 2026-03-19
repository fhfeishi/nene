// src/features/voice-call/components/VoiceCallModal.tsx

import React, { useEffect, useState, useRef, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { MicOff, Mic, MessageSquare } from 'lucide-react';
import { useAppStore } from '../../../store/useAppStore';
import { CallVisualizer } from './CallVisualizer';

type CallPhase = 'listening' | 'thinking' | 'speaking';

const PHASE_LABELS: Record<CallPhase, string> = {
    listening: '正在倾听',
    thinking:  '思考中',
    speaking:  '正在回复',
};

const PHASE_CYCLE: CallPhase[] = ['listening', 'thinking', 'speaking', 'listening'];

// 长按触发挂断的时长（ms）
const HOLD_DURATION = 700;
// SVG 进度环周长：r=32 → 2π×32 ≈ 201
const RING_CIRCUMFERENCE = 201;

export const VoiceCallModal: React.FC = () => {
    const { isVoiceCallActive, setVoiceCallActive } = useAppStore();
    const [isMuted, setIsMuted] = useState(false);
    const [seconds, setSeconds] = useState(0);
    const [phase, setPhase]     = useState<CallPhase>('listening');

    const timerRef  = useRef<ReturnType<typeof setInterval> | null>(null);
    const phaseRef  = useRef<ReturnType<typeof setInterval> | null>(null);
    const phaseIdx  = useRef(0);

    useEffect(() => {
        if (!isVoiceCallActive) return;
        setSeconds(0); setPhase('listening'); phaseIdx.current = 0;
        timerRef.current = setInterval(() => setSeconds(s => s + 1), 1000);
        phaseRef.current = setInterval(() => {
            phaseIdx.current = (phaseIdx.current + 1) % PHASE_CYCLE.length;
            setPhase(PHASE_CYCLE[phaseIdx.current]);
        }, 2800);
        return () => {
            clearInterval(timerRef.current!);
            clearInterval(phaseRef.current!);
        };
    }, [isVoiceCallActive]);

    const formatTime = (s: number) =>
        `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`;

    return (
        <AnimatePresence>
            {isVoiceCallActive && (
                <motion.div
                    initial={{ opacity: 0, y: '100%' }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: '100%' }}
                    transition={{ type: 'spring', stiffness: 72, damping: 18 }}
                    className="fixed inset-0 z-50 bg-[#0f1117] flex flex-col text-slate-200"
                >
                    {/* Header：纯状态展示 */}
                    <header className="h-14 flex items-center justify-between px-6">
                        <div className="flex items-center gap-2">
                            <span className="w-[7px] h-[7px] rounded-full bg-emerald-500 animate-pulse" />
                            <span className="text-[11px] text-slate-500 tracking-[.04em]">语音对话中</span>
                        </div>
                        <span className="text-[11px] text-slate-600 tabular-nums">{formatTime(seconds)}</span>
                    </header>

                    {/* Body */}
                    <div className="flex-1 flex flex-col items-center justify-center gap-7">
                        {/* 头像 + 脉冲环 */}
                        <div className="relative w-24 h-24 flex items-center justify-center">
                            {[0, 1, 2].map(i => (
                                <motion.div key={i}
                                            className="absolute inset-0 rounded-full border border-indigo-500/15"
                                            animate={{ scale: [0.7, 1.65], opacity: [0.35, 0] }}
                                            transition={{ duration: 3, delay: i, repeat: Infinity, ease: 'easeOut' }}
                                />
                            ))}
                            <div className="w-[68px] h-[68px] rounded-full bg-[#1a1d27] border border-indigo-500/20 flex items-center justify-center z-10">
                                {/* 替换为你的品牌图标 */}
                                <svg width="26" height="26" viewBox="0 0 32 32" fill="none">
                                    <circle cx="16" cy="16" r="13" fill="rgba(99,102,241,.12)"/>
                                    <path d="M11 13h10M11 17h6" stroke="rgba(99,102,241,.85)" strokeWidth="1.6" strokeLinecap="round"/>
                                    <circle cx="20" cy="19" r="3" fill="rgba(99,102,241,.6)"/>
                                </svg>
                            </div>
                        </div>

                        <div className="text-center">
                            <p className="text-[15px] font-medium text-slate-200 mb-1.5">智能助手</p>
                            <motion.p
                                key={isMuted ? 'muted' : phase}
                                initial={{ opacity: 0, y: 3 }}
                                animate={{ opacity: 1, y: 0 }}
                                className="text-[11px] text-slate-500"
                            >
                                {isMuted ? '已静音' : PHASE_LABELS[phase]}
                            </motion.p>
                        </div>

                        <CallVisualizer state={isMuted ? 'thinking' : phase} />
                    </div>

                    {/* Footer */}
                    <footer className="pb-10 px-8">
                        <div className="flex items-center justify-between mb-4">

                            {/* 静音按钮 56px */}
                            <motion.button
                                onClick={() => setIsMuted(m => !m)}
                                whileTap={{ scale: 0.88 }}
                                className={[
                                    'w-14 h-14 rounded-full flex items-center justify-center border transition-all duration-200',
                                    isMuted
                                        ? 'bg-red-500/10 border-red-500/25 text-red-400'
                                        : 'bg-white/[.04] border-white/[.07] text-slate-400',
                                ].join(' ')}
                            >
                                {isMuted ? <MicOff size={20} /> : <Mic size={20} />}
                            </motion.button>

                            {/* 长按挂断按钮 72px + 进度环 */}
                            <HoldToHangUp onEnd={() => setVoiceCallActive(false)} />

                            {/* 切换文字模式 56px */}
                            <motion.button
                                onClick={() => setVoiceCallActive(false)}
                                whileTap={{ scale: 0.88 }}
                                className="w-14 h-14 rounded-full flex items-center justify-center border bg-white/[.04] border-white/[.07] text-slate-400"
                            >
                                <MessageSquare size={20} />
                            </motion.button>
                        </div>

                        {/* 底部提示 */}
                        <p className="text-center text-[10px] text-slate-700">长按挂断</p>
                    </footer>
                </motion.div>
            )}
        </AnimatePresence>
    );
};

// ─── HoldToHangUp ────────────────────────────────────────────────
// 长按 HOLD_DURATION ms 后触发，松手则重置进度环
interface HoldProps { onEnd: () => void; }

const HoldToHangUp: React.FC<HoldProps> = ({ onEnd }) => {
    const [progress, setProgress] = useState(0);   // 0 → 1
    const rafRef   = useRef<number | null>(null);
    const startRef = useRef<number | null>(null);

    const startHold = useCallback(() => {
        startRef.current = performance.now();
        const tick = () => {
            const p = Math.min((performance.now() - startRef.current!) / HOLD_DURATION, 1);
            setProgress(p);
            if (p >= 1) { onEnd(); return; }
            rafRef.current = requestAnimationFrame(tick);
        };
        rafRef.current = requestAnimationFrame(tick);
    }, [onEnd]);

    const cancelHold = useCallback(() => {
        if (rafRef.current) cancelAnimationFrame(rafRef.current);
        startRef.current = null;
        setProgress(0);
    }, []);

    // 进度环 strokeDashoffset：从全偏移（空）→ 0（满）
    const offset = RING_CIRCUMFERENCE * (1 - progress);
    const isHolding = progress > 0;

    return (
        <div className="relative w-[72px] h-[72px] flex items-center justify-center flex-shrink-0">
            {/* SVG 进度环 */}
            <svg
                className="absolute inset-0 -rotate-90"
                width="72" height="72" viewBox="0 0 72 72"
            >
                {/* 轨道 */}
                <circle cx="36" cy="36" r="32"
                        fill="none" stroke="rgba(239,68,68,.15)" strokeWidth="3" />
                {/* 进度 */}
                <circle cx="36" cy="36" r="32"
                        fill="none"
                        stroke="#ef4444"
                        strokeWidth="3"
                        strokeDasharray={RING_CIRCUMFERENCE}
                        strokeDashoffset={offset}
                        strokeLinecap="round"
                        style={{ transition: isHolding ? 'none' : 'stroke-dashoffset .25s ease' }}
                />
            </svg>

            {/* 挂断按钮 */}
            <motion.button
                animate={{ scale: isHolding ? 0.92 : 1 }}
                transition={{ duration: 0.1 }}
                className="w-[60px] h-[60px] rounded-full bg-red-500 flex items-center justify-center z-10 cursor-pointer select-none"
                style={{ background: isHolding ? '#dc2626' : '#ef4444' }}
                onMouseDown={startHold}
                onMouseUp={cancelHold}
                onMouseLeave={cancelHold}
                onTouchStart={startHold}
                onTouchEnd={cancelHold}
            >
                <svg width="22" height="22" viewBox="0 0 24 24" fill="none"
                     stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M10.68 13.31a16 16 0 003.41 2.6l1.27-1.27a2 2 0 012.11-.45
                             c.907.34 1.85.57 2.81.7A2 2 0 0122 18.92v3a2 2 0 01-2.18 2
                             19.79 19.79 0 01-8.63-3.07A19.42 19.42 0 013.43 9.19
                             19.79 19.79 0 01.36 10.44 2 2 0 012 8.26V5.26
                             a2 2 0 011.72-2c.96.127 1.9.361 2.81.7
                             a2 2 0 01.45 2.11L5.73 7.34"/>
                </svg>
            </motion.button>
        </div>
    );
};