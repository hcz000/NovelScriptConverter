<template>
  <section class="page">
    <header class="page-header">
      <div>
        <p class="eyebrow">Project Hub</p>
        <h2>项目列表</h2>
      </div>
      <StatusBanner :active="store.loading" :text="store.message" />
    </header>

    <section class="card">
      <div class="panel-header">
        <h3>项目</h3>
        <div class="button-row">
          <label class="toggle-field">
            <input v-model="includeArchived" type="checkbox" @change="loadProjects" />
            <span>显示归档</span>
          </label>
          <button class="ghost-button" @click="loadProjects">刷新</button>
        </div>
      </div>

      <div v-if="!store.projects.length" class="empty-state">
        <p>还没有项目。</p>
      </div>

      <ul v-else class="project-list">
        <li v-for="project in store.projects" :key="project.project_id" class="project-row">
          <button
            class="project-main"
            :class="{ selected: project.project_id === store.projectId }"
            @click="openProject(project.project_id)"
          >
            <strong>{{ project.title }}</strong>
            <span>{{ project.status }} / 版本 {{ project.version_count }}</span>
            <span>更新：{{ project.updated_at }}</span>
          </button>
          <div class="project-actions">
            <template v-if="project.archived">
              <button class="ghost-button" :disabled="store.loading" @click="unarchiveProject(project)">
                取消归档
              </button>
            </template>
            <button
              v-else
              class="ghost-button"
              :disabled="store.loading"
              @click="archiveProject(project)"
            >
              归档
            </button>
            <button class="ghost-button danger-button" :disabled="store.loading" @click="deleteProject(project)">
              删除
            </button>
          </div>
        </li>
      </ul>
    </section>
  </section>
</template>

<!-- 项目列表页面：展示所有项目，支持筛选、切换、归档和删除操作 -->
<script setup>
import { onMounted, ref } from "vue";
import { useRouter } from "vue-router";

import StatusBanner from "../components/StatusBanner.vue";
import { useProjectStore } from "../stores/project";

const router = useRouter();
const store = useProjectStore();
const includeArchived = ref(false);  // 是否显示已归档项目

/** 加载项目列表 */
async function loadProjects() {
  await store.loadProjects(includeArchived.value);
}

/** 打开指定项目并跳转到工作台 */
async function openProject(projectId) {
  await store.switchProject(projectId);
  await router.push("/workspace");
}

/** 归档项目（需确认） */
async function archiveProject(project) {
  if (!window.confirm(`确认归档项目“${project.title}”？`)) {
    return;
  }
  await store.archiveActiveProject(project.project_id);
}

/** 取消归档 */
async function unarchiveProject(project) {
  await store.unarchiveActiveProject(project.project_id);
}

/** 删除项目（需确认，不可恢复） */
async function deleteProject(project) {
  if (!window.confirm(`确认删除项目“${project.title}”？此操作不可恢复。`)) {
    return;
  }
  await store.deleteActiveProject(project.project_id);
}

// 组件挂载时自动加载项目列表
onMounted(loadProjects);
</script>
