<template>
  <section class="page">
    <header class="page-header">
      <div>
        <p class="eyebrow">Phase 3</p>
        <h2>版本记录</h2>
      </div>
      <StatusBanner :active="store.loading" :text="store.message" />
    </header>

    <div v-if="!store.hasProject" class="empty-state">
      <p>当前没有项目数据。</p>
    </div>

    <div v-else class="grid two-columns">
      <article class="card">
        <div class="panel-header">
          <h3>版本列表</h3>
          <button class="ghost-button" @click="store.refreshAll">刷新</button>
        </div>
        <ul class="version-list">
          <li v-for="version in store.versions" :key="version.version_id">
            <button
              class="scene-item"
              :class="{ selected: store.activeVersionId === version.version_id }"
              @click="selectVersion(version.version_id)"
            >
              <strong>{{ version.version_name }}</strong>
              <p>{{ version.description }}</p>
              <p>改动场景：{{ version.modified_scenes?.length || 0 }}</p>
              <span>{{ version.created_at }}</span>
            </button>
          </li>
        </ul>
      </article>
      <article class="card">
        <h3>当前查看</h3>
        <p v-if="store.activeVersion">
          版本：{{ store.activeVersion.version_name }}
        </p>
        <p v-if="store.activeVersion">
          说明：{{ store.activeVersion.description }}
        </p>
        <p v-if="!store.activeVersion">尚未选择版本</p>

        <h3>章节概览</h3>
        <ul class="version-list">
          <li v-for="chapter in store.chapters" :key="chapter.chapter_id">
            <strong>{{ chapter.title }}</strong>
            <p>{{ chapter.summary }}</p>
          </li>
        </ul>
      </article>
      <article class="card compare-card">
        <h3>版本对比</h3>
        <div class="compare-controls">
          <label class="field">
            <span>基准版本</span>
            <select v-model="baseVersionId">
              <option value="">选择版本</option>
              <option v-for="version in store.versions" :key="`base-${version.version_id}`" :value="version.version_id">
                {{ version.version_name }}
              </option>
            </select>
          </label>
          <label class="field">
            <span>目标版本</span>
            <select v-model="targetVersionId">
              <option value="">选择版本</option>
              <option
                v-for="version in store.versions"
                :key="`target-${version.version_id}`"
                :value="version.version_id"
              >
                {{ version.version_name }}
              </option>
            </select>
          </label>
          <button class="primary-button" :disabled="!canCompare || store.loading" @click="compareVersions">
            对比
          </button>
        </div>

        <div v-if="store.versionCompare" class="compare-result">
          <div class="summary-grid">
            <span>新增 {{ store.versionCompare.summary.added }}</span>
            <span>删除 {{ store.versionCompare.summary.removed }}</span>
            <span>修改 {{ store.versionCompare.summary.changed }}</span>
            <span>未变 {{ store.versionCompare.summary.unchanged }}</span>
          </div>
          <ul class="version-list">
            <li v-for="scene in changedScenes" :key="scene.scene_id" class="diff-row">
              <strong>{{ scene.scene_id }} {{ scene.title }}</strong>
              <span>{{ statusLabel(scene.status) }}</span>
              <p v-if="scene.changed_fields.length">字段：{{ scene.changed_fields.join("、") }}</p>
            </li>
          </ul>
          <p v-if="!changedScenes.length" class="muted-text">两个版本的场景内容没有差异。</p>
        </div>
      </article>
    </div>
  </section>
</template>

<!-- 版本记录页面：展示版本列表、章节概览和版本差异对比 -->
<script setup>
import { computed, ref, watch } from "vue";

import StatusBanner from "../components/StatusBanner.vue";
import { useProjectStore } from "../stores/project";

const store = useProjectStore();
const baseVersionId = ref("");     // 基准版本 ID（对比用）
const targetVersionId = ref("");   // 目标版本 ID（对比用）

/** 是否可以进行对比：两个版本都已选择且不同 */
const canCompare = computed(
  () => baseVersionId.value && targetVersionId.value && baseVersionId.value !== targetVersionId.value
);

/** 过滤出有变化的场景（排除 unchanged 状态） */
const changedScenes = computed(() =>
  (store.versionCompare?.scenes || []).filter((scene) => scene.status !== "unchanged")
);

/** 监听版本列表变化，自动填充默认对比版本 */
watch(
  () => store.versions,
  (versions) => {
    if (!versions.length) {
      baseVersionId.value = "";
      targetVersionId.value = "";
      return;
    }
    if (!baseVersionId.value && versions.length >= 1) {
      baseVersionId.value = versions[0].version_id;
    }
    if (!targetVersionId.value && versions.length >= 2) {
      targetVersionId.value = versions[versions.length - 1].version_id;
    }
  },
  { immediate: true }
);

/** 选择版本并刷新项目数据 */
async function selectVersion(versionId) {
  await store.selectVersion(versionId);
}

/** 执行版本对比 */
async function compareVersions() {
  await store.compareVersionPair(baseVersionId.value, targetVersionId.value);
}

/** 状态码转中文标签 */
function statusLabel(status) {
  return {
    added: "新增",
    removed: "删除",
    changed: "修改",
    unchanged: "未变"
  }[status] || status;
}
</script>
