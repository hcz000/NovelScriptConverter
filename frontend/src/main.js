/** 前端应用入口：创建 Vue 3 应用，注册 Pinia 状态管理和 Vue Router。 */
import { createApp } from "vue";
import { createPinia } from "pinia";

import App from "./App.vue";
import router from "./router";
import "./style.css";

const app = createApp(App);

app.use(createPinia());   // 注册状态管理
app.use(router);           // 注册路由
app.mount("#app");         // 挂载到 #app 元素
