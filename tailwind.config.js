// 主题色都是 CSS 变量，Tailwind 拆不出颜色通道，bg-primary/20 这类透明度写法原本不生成样式。
// 带透明度修饰符时改用 color-mix 混合；不带时仍输出原样的 var(--xxx)。
const themeColor = (name) => ({ opacityValue }) =>
  opacityValue === undefined || String(opacityValue).startsWith("var(")
    ? `var(--${name})`
    : `color-mix(in srgb, var(--${name}) ${Number(opacityValue) * 100}%, transparent)`;

// Material You 色彩角色，生成 bg-primary-container、text-on-surface-variant 这类工具类
const M3_ROLES = [
  "primary", "on-primary", "primary-container", "on-primary-container",
  "secondary", "on-secondary", "secondary-container", "on-secondary-container",
  "tertiary", "on-tertiary", "tertiary-container", "on-tertiary-container",
  "error", "on-error", "error-container", "on-error-container",
  "surface", "on-surface", "surface-variant", "on-surface-variant",
  "surface-dim", "surface-bright", "surface-container-lowest", "surface-container-low",
  "surface-container", "surface-container-high", "surface-container-highest",
  "outline", "outline-variant", "inverse-surface", "inverse-on-surface", "inverse-primary",
  "scrim", "rise", "fall",
];
const m3Colors = Object.fromEntries(M3_ROLES.map((role) => [`md-${role}`, themeColor(`md-${role}`)]));

/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{vue,js,ts,jsx,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        ...m3Colors,
        // 旧页面用的 shadcn 风格名字，在 theme.css 里已映射到 M3 角色
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
        // 旧版页面和案例管理里的「高达配色」，改为跟随主题的色彩角色
        "gundam-blue": themeColor("md-primary"),
        "gundam-red": themeColor("md-error"),
        "gundam-yellow": themeColor("md-tertiary-container"),
        "gundam-white": themeColor("md-surface-container-low"),
        "gundam-dark-blue": themeColor("md-on-primary-container"),
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
      // M3 圆角刻度：页面里现成的 rounded-md / rounded-lg 自动变得更圆润
      borderRadius: {
        sm: "6px",
        DEFAULT: "8px",
        md: "12px",
        lg: "16px",
        xl: "20px",
        "2xl": "28px",
        "3xl": "32px",
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
        "md-1": "var(--md-elevation-1)",
        "md-2": "var(--md-elevation-2)",
        "md-3": "var(--md-elevation-3)",
        "md-4": "var(--md-elevation-4)",
        "md-5": "var(--md-elevation-5)",
      },
      transitionTimingFunction: {
        standard: "var(--md-ease-standard)",
        emphasized: "var(--md-ease-emphasized)",
        decelerate: "var(--md-ease-emphasized-decelerate)",
        accelerate: "var(--md-ease-emphasized-accelerate)",
        spring: "var(--md-ease-spring)",
      },
    },
  },
  plugins: [],
};
