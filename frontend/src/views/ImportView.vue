<template>
  <section class="page">
    <header class="page-header">
      <div>
        <p class="eyebrow">Phase 1</p>
        <h2>导入小说并生成初稿</h2>
      </div>
      <StatusBanner :active="store.loading" :text="store.message" />
    </header>

    <div class="card form-card">
      <label class="field">
        <span>项目名称</span>
        <input v-model="title" placeholder="输入项目名称" />
      </label>
      <label class="field">
        <span>小说文件</span>
        <input type="file" accept=".txt,.md" @change="onFileChange" />
      </label>
      <button class="primary-button" :disabled="store.loading || !canSubmit" @click="handleSubmit">
        创建项目并生成剧本
      </button>
    </div>

    <div class="grid two-columns">
      <article class="card">
        <h3>流程说明</h3>
        <p>创建项目后会自动执行文件上传、章节解析和 YAML 剧本生成。</p>
        <p>当前实现使用 FastAPI 后端的异步任务轮询接口。</p>
      </article>
      <article class="card">
        <h3>当前项目</h3>
        <p v-if="store.project">{{ store.project.title }}</p>
        <p v-else>尚未创建项目</p>
        <p v-if="store.project">状态：{{ store.project.status }}</p>
      </article>
    </div>
  </section>
</template>

<script setup>
import { computed, ref } from "vue";
import { useRouter } from "vue-router";

import StatusBanner from "../components/StatusBanner.vue";
import { useProjectStore } from "../stores/project";

const router = useRouter();
const store = useProjectStore();
const title = ref("");
const file = ref(null);

const canSubmit = computed(() => title.value.trim() && file.value);

function onFileChange(event) {
  const [selected] = event.target.files || [];
  file.value = selected || null;
}

async function handleSubmit() {
  if (!canSubmit.value) {
    return;
  }
  try {
    await store.bootstrapProject(title.value.trim(), file.value);
    await router.push("/workspace");
  } catch (error) {
    window.alert(error.message || "初始化失败");
  }
}
</script>
