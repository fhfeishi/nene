// src/features/voice-call/components/CallVisualizer.tsx

import React from 'react';
import { motion } from 'framer-motion';

type CallState = 'listening' | 'thinking' | 'speaking';

interface CallVisualizerProps {
    state?: CallState;
}

// 静态配置：高度比例(0-1)、动画时长、延迟
// 使用固定值避免随机数在 SSR/re-render 时产生差异
const BARS: { h: number; dur: number; delay: number }[] = [
    { h: 0.20, dur: 1.1, delay: 0.00 },
    { h: 0.45, dur: 1.3, delay: 0.08 },
    { h: 0.70, dur: 0.9, delay: 0.16 },
    { h: 0.90, dur: 1.2, delay: 0.06 },
    { h: 1.00, dur: 1.0, delay: 0.22 },
    { h: 0.85, dur: 1.4, delay: 0.14 },
    { h: 0.60, dur: 0.95, delay: 0.30 },
    { h: 0.40, dur: 1.15, delay: 0.04 },
    { h: 0.65, dur: 1.05, delay: 0.20 },
    { h: 0.95, dur: 0.85, delay: 0.12 },
    { h: 0.75, dur: 1.25, delay: 0.28 },
    { h: 0.50, dur: 1.0,  delay: 0.10 },
    { h: 0.35, dur: 1.35, delay: 0.18 },
    { h: 0.55, dur: 0.9,  delay: 0.26 },
    { h: 0.30, dur: 1.1,  delay: 0.02 },
    { h: 0.18, dur: 1.2,  delay: 0.24 },
];

const MAX_H = 44; // px，容器高度

export const CallVisualizer: React.FC<CallVisualizerProps> = ({ state = 'listening' }) => {
    const isAnimating = state !== 'thinking';

    return (
        <div
            className="flex items-center gap-[5px]"
            style={{ height: `${MAX_H}px` }}
        >
            {BARS.map((bar, i) => (
                <motion.div
                    key={i}
                    className="w-[3px] rounded-full"
                    style={{
                        // speaking 时用主色，listening 时稍淡
                        background: state === 'speaking'
                            ? `rgba(99,102,241,${0.5 + bar.h * 0.5})`
                            : `rgba(99,102,241,${0.25 + bar.h * 0.3})`,
                        transformOrigin: 'center',
                    }}
                    animate={isAnimating ? {
                        scaleY: [0.15, 1, 0.15],
                    } : {
                        scaleY: 0.12,
                    }}
                    initial={{ scaleY: 0.15, height: `${bar.h * MAX_H}px` }}
                    transition={isAnimating ? {
                        duration: bar.dur,
                        delay: bar.delay,
                        repeat: Infinity,
                        ease: 'easeInOut',
                    } : {
                        duration: 0.4,
                        ease: 'easeOut',
                    }}
                    // 高度决定视觉宽窄分布，scaleY 做动画
                    // 注意：height 固定，scaleY 负责拉伸
                    // 如果希望更饱满可改为 height animated
                />
            ))}
        </div>
    );
};