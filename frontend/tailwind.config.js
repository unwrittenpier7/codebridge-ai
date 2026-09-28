/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        surface: {
          950: '#0b0e14',
          900: '#0f131a',
          800: '#151b24',
          700: '#1d2531',
          600: '#2a3441',
          500: '#3a4552',
        },
        accent: {
          DEFAULT: '#4f9cf9',
          muted: '#2d6ab8',
        },
        pass: '#3fb950',
        fail: '#f85149',
        partial: '#d29922',
      },
      fontFamily: {
        mono: ['JetBrains Mono', 'Fira Code', 'ui-monospace', 'SFMono-Regular', 'monospace'],
      },
    },
  },
  plugins: [],
}
