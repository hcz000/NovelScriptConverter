<template>
  <section class="page">
    <header class="page-header">
      <div>
        <p class="eyebrow">Phase 2</p>
        <h2>剧本工作台</h2>
      </div>
      <StatusBanner :active="store.loading" :text="store.message" />
    </header>

    <div v-if="!store.hasProject" class="empty-state">
      <p>先在导入页创建项目，再进入工作台。</p>
    </div>

    <div v-else class="workspace-grid">
      <aside class="card panel">
        <div class="panel-header">
          <h3>场景列表</h3>
          <button class="ghost-button" @click="store.refreshAll">刷新</button>
        </div>
        <ul class="scene-list">
          <li v-for="scene in store.scenes" :key="scene.scene_id">
            <button
              class="scene-item"
              :class="{ selected: store.selectedSceneId === scene.scene_id }"
              @click="selectScene(scene.scene_id)"
            >
              <strong>{{ scene.title }}</strong>
              <span>{{ scene.scene_id }}</span>
            </button>
          </li>
        </ul>
      </aside>

      <section class="card panel editor-panel">
        <div class="panel-header">
          <h3>场景编辑</h3>
          <button class="primary-button" :disabled="!store.selectedScene" @click="saveScene">保存场景</button>
        </div>
        <div v-if="store.selectedScene" class="editor-form">
          <label class="field">
            <span>标题</span>
            <input v-model="form.title" />
          </label>
          <label class="field">
            <span>场景行</span>
            <input v-model="form.slugline" />
          </label>
          <label class="field">
            <span>场景目标</span>
            <textarea v-model="form.purpose" rows="4" />
          </label>
          <label class="field">
            <span>节拍 JSON</span>
            <textarea v-model="form.beatsText" rows="10" />
          </label>
          <label class="field">
            <span>重写指令</span>
            <textarea v-model="rewriteInstruction" rows="4" placeholder="增强冲突张力，压缩节奏" />
          </label>
          <button class="ghost-button" @click="handleRewrite">执行 AI 重写</button>
        </div>
        <div v-else class="empty-state">
          <p>选择一个场景开始编辑。</p>
        </div>
      </section>

      <aside class="card panel preview-panel">
        <div class="panel-header">
          <h3>YAML 预览</h3>
          <button class="ghost-button" @click="store.runExport()">导出</button>
        </div>
        <pre class="code-block">{{ formattedScript }}</pre>
        <div v-if="store.exportResult" class="export-box">
          <p>导出完成</p>
          <a :href="store.exportResult.download_url" target="_blank" rel="noreferrer">
            {{ store.exportResult.file_name }}
          </a>
        </div>
      </aside>
    </div>
  </section>
</template>

<script setup>
import { computed, reactive, ref, watch } from "vue";

import StatusBanner from "../components/StatusBanner.vue";
import { useProjectStore } from "../stores/project";

const store = useProjectStore();
const rewriteInstruction = ref("");
const form = reactive({
  title: "",
  slugline: "",
  purpose: "",
  beatsText: "[]"
});

const formattedScript = computed(() => {
  if (!store.script) {
    return "暂无剧本数据";
  }
  return JSON.stringify(store.script, null, 2);
});

watch(
  () => store.selectedScene,
  (scene) => {
    if (!scene) {
      return;
    }
    form.title = scene.title || "";
    form.slugline = scene.slugline || "";
    form.purpose = scene.purpose || "";
    form.beatsText = JSON.stringify(scene.beats || [], null, 2);
  },
  {
    immediate: true
  }
);

async function selectScene(sceneId) {
  await store.loadScene(sceneId);
}

async function saveScene() {
  try {
    await store.saveScene({
      title: form.title,
      slugline: form.slugline,
      purpose: form.purpose,
      beats: JSON.parse(form.beatsText),
      change_note: "前端工作台保存"
    });
  } catch (error) {
    window.alert(error.message || "保存失败");
  }
}

async function handleRewrite() {
  if (!rewriteInstruction.value.trim()) {
    window.alert("请输入重写指令");
    return;
  }
  try {
    await store.runRewrite(rewriteInstruction.value.trim());
    rewriteInstruction.value = "";
  } catch (error) {
    window.alert(error.message || "重写失败");
  }
}
</script>
