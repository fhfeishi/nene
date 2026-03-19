// src/store/useAppStore.ts

import { create } from 'zustand';
import { persist } from 'zustand/middleware';

interface AppState {
    theme: 'light' | 'dark';
    toggleTheme: () => void;
    isVoiceCallActive: boolean;
    setVoiceCallActive: (active: boolean) => void;
}

export const useAppStore = create<AppState>()(
    persist(
        (set) => ({
            theme: 'light',
            isVoiceCallActive: false, // 默认关闭

            toggleTheme: () => set((state) => {
                const newTheme = state.theme === 'light' ? 'dark' : 'light';
                document.documentElement.classList.toggle('dark', newTheme === 'dark');
                return { theme: newTheme };
            }),

            // === 新增：操作方法 ===
            setVoiceCallActive: (active) => set({ isVoiceCallActive: active }),
        }),
        {
            name: 'app-storage',
            partialize: (state) => ({ theme: state.theme }), // 只持久化主题，不持久化通话状态
        }
    )
);