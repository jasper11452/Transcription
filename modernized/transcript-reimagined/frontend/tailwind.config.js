/** @type {import('tailwindcss').Config} */

// 设计语言来源：/DESIGN.md（xAI 风格解析）
// —— 近黑画布 #0a0a0a、白色胶囊描边按钮、#191919 卡片 + 发丝线边框、
//    无阴影层级、Display 400 字重 + 负字距、等宽大写字距作眉题。
// 深浅主题变量定义在 src/index.css；两个页面共用 public/theme.js。
export default {
  content: ['./index.html', './task.html', './public/theme.js', './src/**/*.{ts,tsx,js,jsx}'],
  theme: {
    extend: {
      colors: {
        border: 'var(--border)',
        input: 'var(--input)',
        ring: 'var(--ring)',
        background: 'var(--background)',
        foreground: 'var(--foreground)',
        primary: {
          DEFAULT: 'var(--primary)',
          foreground: 'var(--primary-foreground)',
        },
        secondary: {
          DEFAULT: 'var(--secondary)',
          foreground: 'var(--secondary-foreground)',
        },
        destructive: {
          DEFAULT: 'var(--destructive)',
          foreground: 'var(--destructive-foreground)',
        },
        muted: {
          DEFAULT: 'var(--muted)',
          foreground: 'var(--muted-foreground)',
        },
        accent: {
          DEFAULT: 'var(--accent)',
          foreground: 'var(--accent-foreground)',
        },
        popover: {
          DEFAULT: 'var(--popover)',
          foreground: 'var(--popover-foreground)',
        },
        card: {
          DEFAULT: 'var(--card)',
          foreground: 'var(--card-foreground)',
        },
        // DESIGN.md colors 原文
        canvas: 'var(--canvas)',
        'canvas-soft': 'var(--canvas-soft)',
        'canvas-card': 'var(--canvas-card)',
        'canvas-mid': 'var(--canvas-mid)',
        hairline: 'var(--hairline)',
        'surface-hover': 'var(--surface-hover)',
        'surface-selected': 'var(--surface-selected)',
        ink: 'var(--ink)',
        'ink-hover': 'var(--ink-hover)',
        body: 'var(--body)',
        mute: 'var(--mute)',
        sunset: 'var(--sunset)',
        'sunset-soft': 'var(--sunset-soft)',
        dusk: 'var(--dusk)',
        twilight: 'var(--twilight)',
        breeze: 'var(--breeze)',
        midnight: 'var(--midnight)',
      },
      fontFamily: {
        // Universal Sans 的替身：Inter 400 + 中文回退 PingFang SC
        sans: [
          'Inter',
          '-apple-system',
          'BlinkMacSystemFont',
          'SF Pro Text',
          'Helvetica Neue',
          'PingFang SC',
          'Hiragino Sans GB',
          'Microsoft YaHei',
          'sans-serif',
        ],
        // caption-mono：Geist Mono 大写 + 1.2~1.4px 字距
        mono: [
          'Geist Mono',
          'ui-monospace',
          'SFMono-Regular',
          'Menlo',
          'Monaco',
          'Consolas',
          'monospace',
        ],
      },
      borderRadius: {
        lg: 'var(--radius)',
        md: 'calc(var(--radius) - 2px)',
        sm: 'calc(var(--radius) - 4px)',
      },
      // display 字号的负字距（-2.4px@96 ≈ -0.025em，-0.6px@32 ≈ -0.019em）
      letterSpacing: {
        display: '-0.02em',
        heading: '-0.01em',
      },
    },
  },
  plugins: [],
}
