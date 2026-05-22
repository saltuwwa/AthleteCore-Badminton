/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx,js,jsx}'],
  theme: {
    extend: {
      colors: {
        bg: '#080a10',
        bg2: '#0f1118',
        bg3: '#161a24',
        bg4: '#1d2230',
        accent: '#7c6bff',
        accent2: '#b8ff6b',
        accent3: '#ff6b8a',
        textPrimary: '#e8e4f0',
        muted: '#6b6880',
        muted2: '#9892a8',
      },
    },
  },
  plugins: [],
}
