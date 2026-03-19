import React, { useEffect } from 'react';
import { Sun, Moon } from 'lucide-react';
import { motion } from 'framer-motion';
import { useAppStore } from '../../store/useAppStore';

export const ThemeToggle = () => {
    const { theme, toggleTheme } = useAppStore();

    // 初始化时确保 class 与状态同步
    useEffect(() => {
        document.documentElement.classList.toggle('dark', theme === 'dark');
    }, []);

    return (
        <motion.button
            onClick={toggleTheme}
            className="p-2 rounded-xl bg-brand-surface border border-brand-border text-brand-text shadow-sm hover:shadow-md transition-all flex items-center justify-center"
            whileTap={{ scale: 0.9 }}
            whileHover={{ rotate: 5 }}
        >
            <div className="relative w-5 h-5">
                <motion.div
                    initial={false}
                    animate={{
                        rotate: theme === 'dark' ? 0 : 90,
                        opacity: theme === 'dark' ? 1 : 0,
                        scale: theme === 'dark' ? 1 : 0.5
                    }}
                    className="absolute inset-0 text-yellow-500"
                >
                    <Moon size={20} fill="currentColor" />
                </motion.div>

                <motion.div
                    initial={false}
                    animate={{
                        rotate: theme === 'light' ? 0 : -90,
                        opacity: theme === 'light' ? 1 : 0,
                        scale: theme === 'light' ? 1 : 0.5
                    }}
                    className="absolute inset-0 text-orange-500"
                >
                    <Sun size={20} fill="currentColor" />
                </motion.div>
            </div>
        </motion.button>
    );
};