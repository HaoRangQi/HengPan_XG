// 主题色是 var(--xxx) 形式的 oklch，Tailwind 拆不出通道，bg-primary/20 这类写法原本不生成任何样式。
// 带透明度修饰符时改用 color-mix 混合；不带时仍输出原样的 var(--xxx)。
const themeColor = (name) => ({ opacityValue }) =>
  opacityValue === undefined || String(opacityValue).startsWith("var(")
    ? `var(--${name})`
    : `color-mix(in oklch, var(--${name}) ${Number(opacityValue) * 100}%, transparent)`;

/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{vue,js,ts,jsx,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        background: themeColor("background"),
        foreground: themeColor("foreground"),
        card: themeColor("card"),
        "card-foreground": themeColor("card-foreground"),
        primary: themeColor("primary"),
        "primary-foreground": themeColor("primary-foreground"),
        secondary: themeColor("secondary"),
        "secondary-foreground": themeColor("secondary-foreground"),
        muted: themeColor("muted"),
        "muted-foreground": themeColor("muted-foreground"),
        accent: themeColor("accent"),
        "accent-foreground": themeColor("accent-foreground"),
        destructive: themeColor("destructive"),
        "destructive-foreground": themeColor("destructive-foreground"),
        border: themeColor("border"),
        input: themeColor("input"),
        ring: themeColor("ring"),
        // 高达主题颜色
        "gundam-blue": "#0066b3", // RX-78-2 蓝色
        "gundam-red": "#e60012", // RX-78-2 红色
        "gundam-yellow": "#fcd000", // RX-78-2 黄色
        "gundam-white": "#f3f3f3", // RX-78-2 白色
        "gundam-dark-blue": "#003a70", // 深蓝色变体
        // 图表颜色
        "chart-1": themeColor("chart-1"),
        "chart-2": themeColor("chart-2"),
        "chart-3": themeColor("chart-3"),
        "chart-4": themeColor("chart-4"),
        "chart-5": themeColor("chart-5"),
      },
      fontFamily: {
        sans: ["var(--font-sans)"],
        serif: ["var(--font-serif)"],
        mono: ["var(--font-mono)"],
      },
      borderRadius: {
        DEFAULT: "var(--radius)",
      },
      boxShadow: {
        "2xs": "var(--shadow-2xs)",
        xs: "var(--shadow-xs)",
        sm: "var(--shadow-sm)",
        DEFAULT: "var(--shadow)",
        md: "var(--shadow-md)",
        lg: "var(--shadow-lg)",
        xl: "var(--shadow-xl)",
        "2xl": "var(--shadow-2xl)",
      },
    },
  },
  plugins: [],
};
