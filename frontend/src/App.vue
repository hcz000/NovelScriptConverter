<template>
  <div class="shell">
    <aside class="sidebar">
      <div class="brand">
        <p class="eyebrow">AI Adaptation Studio</p>
        <h1>小说改编工作台</h1>
      </div>
      <nav class="nav">
        <RouterLink to="/">导入</RouterLink>
        <RouterLink to="/projects">项目</RouterLink>
        <RouterLink to="/workspace">工作台</RouterLink>
        <RouterLink to="/versions">版本</RouterLink>
      </nav>
      <section class="meta">
        <p>技术栈</p>
        <strong>FastAPI + Vue 3 + Vite</strong>
      </section>
    </aside>
    <main class="main">
      <RouterView />
    </main>
  </div>
</template>

<!-- 根组件：应用外壳布局，包含左侧导航和主内容区 -->
<script setup>
import { onMounted } from "vue";
import { RouterLink, RouterView } from "vue-router";

import { useProjectStore } from "./stores/project";

const store = useProjectStore();

// 组件挂载时自动恢复上次项目状态
onMounted(() => {
  store.hydrateProject();
});
</script>
