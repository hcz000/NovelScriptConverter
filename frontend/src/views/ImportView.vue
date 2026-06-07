<template>
  <section class="import-page">
    <!-- 顶部标题区 -->
    <div class="import-hero">
      <div class="hero-badge">Step 1 → 3</div>
      <h2>智能剧本改编</h2>
      <p class="hero-desc">上传小说，AI 自动解析章节、提取人物、生成场景化剧本草稿</p>

      <!-- 工作流步骤 -->
      <div class="workflow-steps">
        <div class="step">
          <span class="step-icon">📄</span>
          <span>上传小说</span>
        </div>
        <div class="step-arrow">→</div>
        <div class="step">
          <span class="step-icon">🔍</span>
          <span>智能解析</span>
        </div>
        <div class="step-arrow">→</div>
        <div class="step">
          <span class="step-icon">🎬</span>
          <span>生成剧本</span>
        </div>
      </div>
    </div>

    <!-- 主表单区 -->
    <div class="import-main">
      <div class="import-form-card">
        <!-- 项目名称 -->
        <label class="field">
          <span>项目名称</span>
          <input
            v-model="title"
            placeholder="给你的项目起个名字，如「斗破苍穹·第一季」"
            class="title-input"
            @keyup.enter="handleSubmit"
          />
        </label>

        <!-- 文件上传区 -->
        <div
          class="upload-zone"
          :class="{ 'upload-zone--active': dragging, 'upload-zone--has-file': file }"
          @dragover.prevent="dragging = true"
          @dragleave.prevent="dragging = false"
          @drop.prevent="onDrop"
        >
          <div v-if="!file" class="upload-placeholder">
            <span class="upload-icon">📂</span>
            <p class="upload-text">拖拽小说文件到此处，或点击下方按钮选择</p>
            <p class="upload-hint">支持 .txt / .md 格式，UTF-8 或 GBK 编码均可</p>
          </div>
          <div v-else class="upload-file-info">
            <span class="upload-icon">📖</span>
            <div>
              <strong>{{ file.name }}</strong>
              <span>{{ formatFileSize(file.size) }}</span>
            </div>
            <button class="upload-remove" @click="clearFile">✕</button>
          </div>
          <input
            ref="fileInput"
            type="file"
            accept=".txt,.md"
            class="upload-input-hidden"
            @change="onFileChange"
          />
          <button v-if="!file" class="file-pick-btn" @click="fileInput?.click()">选择文件</button>
        </div>

        <!-- 提交按钮 -->
        <button
          class="submit-btn"
          :disabled="store.loading || !canSubmit"
          @click="handleSubmit"
        >
          <span v-if="store.loading" class="spinner"></span>
          <span v-else>🚀</span>
          {{ store.loading ? store.message : '开始生成剧本' }}
        </button>
      </div>

      <!-- 项目状态栏 -->
      <div v-if="store.hasProject" class="project-status-bar">
        <div class="project-status-dot" :class="store.project?.status?.toLowerCase()"></div>
        <span class="project-status-label">当前项目</span>
        <strong>{{ store.project?.title }}</strong>
        <span class="divider">|</span>
        <span class="status-text">{{ statusLabel(store.project?.status) }}</span>
        <button class="status-action" @click="router.push('/workspace')">进入工作台 →</button>
      </div>
    </div>
  </section>
</template>

<!-- 导入页面：拖拽上传小说文件，一键创建项目并生成剧本初稿 -->
<script setup>
import { computed, ref } from "vue";
import { useRouter } from "vue-router";

import { useProjectStore } from "../stores/project";

const router = useRouter();
const store = useProjectStore();
const title = ref("");            // 项目名称
const file = ref(null);           // 选中的文件对象
const dragging = ref(false);      // 是否正在拖拽文件
const fileInput = ref(null);      // 隐藏的 <input type="file"> 引用

/** 只有项目名称和文件都填写后才能提交 */
const canSubmit = computed(() => title.value.trim() && file.value);

/** 文件选择（click） */
function onFileChange(event) {
  const [selected] = event.target.files || [];
  file.value = selected || null;
}

/** 文件拖放 */
function onDrop(event) {
  dragging.value = false;
  const [dropped] = event.dataTransfer.files || [];
  if (dropped) {
    file.value = dropped;
  }
}

/** 清空文件 */
function clearFile() {
  file.value = null;
  if (fileInput.value) {
    fileInput.value.value = '';
  }
}

/** 文件大小格式化 */
function formatFileSize(bytes) {
  if (!bytes) return '';
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

/** 状态翻译 */
function statusLabel(status) {
  const map = {
    INIT: '等待上传',
    SOURCE_UPLOADED: '文件已上传',
    PARSING: '正在解析章节',
    READY: '待生成剧本',
    GENERATING: '正在生成剧本',
    SCRIPT_READY: '剧本已就绪',
    ARCHIVED: '已归档',
  };
  return map[status] || status;
}

/** 提交创建项目 + 一键流程 */
async function handleSubmit() {
  if (!canSubmit.value) return;
  try {
    await store.bootstrapProject(title.value.trim(), file.value);
    await router.push("/workspace");
  } catch (error) {
    window.alert(error.message || "初始化失败");
  }
}
</script>
