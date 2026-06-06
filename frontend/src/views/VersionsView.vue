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
    </div>
  </section>
</template>

<script setup>
import StatusBanner from "../components/StatusBanner.vue";
import { useProjectStore } from "../stores/project";

const store = useProjectStore();

async function selectVersion(versionId) {
  await store.selectVersion(versionId);
}
</script>
