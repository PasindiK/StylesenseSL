/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        accent: '#4F46E5',
        success: '#10B981',
        darkBg: '#1F1F23',
        darkCard: '#2A2A30',
        darkUserBubble: '#2B2B2B',
        darkBotBubble: '#27272B',
        darkBorder: '#3A3A3F',
        darkHover: '#323239',
        lightBg: '#F9FAFB',
        lightCard: '#FFFFFF',
        lightUserBubble: '#E5E7EB',
        lightBotBubble: '#FFFFFF',
        lightBorder: '#E5E7EB',
        lightHover: '#F3F4F6',
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
      },
    },
  },
  plugins: [],
}
