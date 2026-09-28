import { createApp } from "vue";
import axios from "axios";
import App from "./App.vue";
// 字体和图标都本地打包，不走 Google CDN
import "@fontsource/roboto/400.css";
import "@fontsource/roboto/500.css";
import "@fontsource/roboto/700.css";
import "material-symbols/rounded.css";
import "./assets/main.css"; // Import Tailwind entry
import { parameterTooltips, parameterTutorials } from "./data/parameterHelp";
import { initTheme } from "./ui/theme.js";
import { installRipple, vRipple } from "./ui/ripple.js";
import MIcon from "./ui/MIcon.vue";

// 挂载前先算好主题色，避免首屏闪一下默认配色
initTheme();
installRipple();

// 请求出错时把 error.message 换成中文：后端 detail 优先，其余按网络 / 超时 / 状态码归类
axios.interceptors.response.use(undefined, (error) => {
  const res = error.response;
  const detail = res && res.data && res.data.detail;
  if (!res || (res.status >= 500 && !res.data)) {
    // 没有响应，或开发代理连不上后端（返回空内容的 500）
    error.message = error.code === "ECONNABORTED" ? "请求超时，请稍后重试" : "无法连接后端服务，请确认后端已在 18001 端口启动";
  } else if (typeof detail === "string" && detail) {
    error.message = detail;
  } else if (res.status === 422) {
    error.message = "请求参数不合法，请检查输入";
  } else {
    error.message = `请求失败（HTTP ${res.status}）`;
  }
  return Promise.reject(error);
});

const app = createApp(App);

// Material You 通用件：<MIcon name="..." /> 和 v-ripple 全局可用
app.component("MIcon", MIcon);
app.directive("ripple", vRipple);

// 提供全局参数帮助数据
app.provide("parameterTooltips", parameterTooltips);
app.provide("parameterTutorials", parameterTutorials);

// 提供全局参数帮助函数
app.provide("parameterHelp", {
  openTutorial: (id) => {
    console.log("全局 openTutorial 被调用:", id);
    // 这个函数会在 ParameterHelpManager 组件挂载后被覆盖
  },
  closeTutorial: () => {
    console.log("全局 closeTutorial 被调用");
    // 这个函数会在 ParameterHelpManager 组件挂载后被覆盖
  },
  getTooltip: (id) => {
    console.log("全局 getTooltip 被调用:", id);
    return parameterTooltips[id] || null;
  },
});

// 添加全局错误处理
app.config.errorHandler = (err, vm, info) => {
  console.error("Vue 错误:", err);
  console.error("组件:", vm);
  console.error("信息:", info);
};

app.mount("#app");
