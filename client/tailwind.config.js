/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        background: '#0b0b0b',
        foreground: '#d1d1d1',
        primary: '#00ff41', // Matrix green
        secondary: '#008f11',
        border: '#333333',
        error: '#ff3131',
      },
      fontFamily: {
        mono: ['JetBrains Mono', 'Fira Code', 'monospace'],
      },
      borderRadius: {
        none: '0',
      }
    },
  },
  plugins: [],
}
